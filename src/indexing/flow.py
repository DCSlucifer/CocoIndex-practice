"""Cocoindex flow theo API 1.x: localfs -> chunk -> embed -> pgvector.

Re-index trigger: đổi EMBED_MODEL_NAME hoặc body của @coco.fn nào đó
=> hash(code) đổi => cocoindex backfill những row bị ảnh hưởng.

Verify reindex bằng cách: set EMBED_MODEL=BGE-large-en-v1.5 và chạy lại.
"""
from __future__ import annotations

import io
import os
import pathlib
import re
import sys
from bisect import bisect_right
from dataclasses import dataclass
from hashlib import sha256
from typing import Annotated, AsyncIterator

import asyncpg
import cocoindex as coco
from cocoindex.connectors import localfs, postgres
from cocoindex.ops.text import RecursiveSplitter
from cocoindex.resources.chunk import Chunk
from cocoindex.resources.file import FileLike, PatternFilePathMatcher
from cocoindex.resources.id import IdGenerator
from numpy.typing import NDArray
from pypdf import PdfReader

from embedding_config import create_indexing_embedder, embedding_config_from_env


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCS_DIR = PROJECT_ROOT / "data" / "docs"
os.environ.setdefault("COCOINDEX_DB", str(PROJECT_ROOT / ".cocoindex"))

# ---- Re-index trigger point ----
EMBED_CONFIG = embedding_config_from_env()
EMBED_MODEL = EMBED_CONFIG.model_name_for_storage

TABLE_NAME = "doc_chunks"
PG_SCHEMA = "rag"

PG_DB = coco.ContextKey[asyncpg.Pool]("rag_pg_db")
EMBEDDER = coco.ContextKey[object]("rag_embedder", detect_change=True)

_splitter = RecursiveSplitter()
INCLUDED_PATTERNS = ["**/*.md", "**/*.txt", "**/*.py", "**/*.pdf"]
EXCLUDED_PATTERNS = ["graphify-out/**", "**/graphify-out/**"]
SECTION_HEADING_RE = re.compile(
    r"(?m)^(?:#{1,6}\s+.+|\d+\.\s+[A-Z][^\n]{2,120})$",
)


def build_path_matcher() -> PatternFilePathMatcher:
    """Build the source-file matcher and exclude generated graphify artifacts."""
    return PatternFilePathMatcher(
        included_patterns=INCLUDED_PATTERNS,
        excluded_patterns=EXCLUDED_PATTERNS,
    )


def _file_to_text(file_bytes: bytes, ext: str) -> str:
    """Convert file bytes to text. PDF qua pypdf, còn lại decode utf-8."""
    if ext == ".pdf":
        reader = PdfReader(io.BytesIO(file_bytes))
        return "\n\n".join(p.extract_text() or "" for p in reader.pages)
    return file_bytes.decode("utf-8", errors="replace")


def _split_lang(ext: str) -> str:
    return {".py": "python", ".md": "markdown", ".txt": "markdown", ".pdf": "markdown"}.get(ext, "markdown")


def _file_to_pages(file_bytes: bytes, ext: str) -> list[str]:
    if ext == ".pdf":
        reader = PdfReader(io.BytesIO(file_bytes))
        return [page.extract_text() or "" for page in reader.pages]
    return [file_bytes.decode("utf-8", errors="replace")]


def _page_starts(pages: list[str]) -> list[int]:
    starts: list[int] = []
    offset = 0
    for index, page in enumerate(pages):
        starts.append(offset)
        offset += len(page)
        if index + 1 < len(pages):
            offset += 2
    return starts


def _page_number_for_offset(page_starts: list[int], offset: int) -> int | None:
    if not page_starts:
        return None
    return max(1, bisect_right(page_starts, offset))


def _section_title_for_offset(text: str, offset: int, end_offset: int | None = None) -> str | None:
    current: str | None = None
    first_inside_span: str | None = None
    for match in SECTION_HEADING_RE.finditer(text):
        if first_inside_span is None and end_offset is not None and offset <= match.start() <= end_offset:
            first_inside_span = match.group(0).strip().lstrip("#").strip()
        if match.start() > offset:
            break
        current = match.group(0).strip().lstrip("#").strip()
    return current or first_inside_span


def _augment_chunk_text(chunk_text: str, section_title: str | None) -> str:
    if not section_title:
        return chunk_text
    return f"Section: {section_title}\n{chunk_text}"


def _chunk_hash(text: str) -> str:
    normalized = " ".join(text.casefold().split())
    return sha256(normalized.encode("utf-8")).hexdigest()


@dataclass
class DocChunk:
    id: int
    source_path: str
    file_type: str
    chunk_start: int
    chunk_end: int
    text: str
    chunk_hash: str
    section_title: str | None
    page_number: int | None
    model_name: str
    embedding: Annotated[NDArray, EMBEDDER]


@coco.lifespan
async def app_lifespan(builder: coco.EnvironmentBuilder) -> AsyncIterator[None]:
    pg_url = os.environ["POSTGRES_URL"]
    async with asyncpg.create_pool(pg_url) as pool:
        async with pool.acquire() as conn:
            await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {PG_SCHEMA}")
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        builder.provide(PG_DB, pool)
        builder.provide(EMBEDDER, create_indexing_embedder(EMBED_CONFIG))
        yield


@coco.fn
async def process_chunk(
    chunk: Chunk,
    source_path: pathlib.PurePath,
    file_type: str,
    full_text: str,
    page_starts: list[int],
    id_gen: IdGenerator,
    table: postgres.TableTarget[DocChunk],
) -> None:
    embedder = coco.use_context(EMBEDDER)
    section_title = _section_title_for_offset(
        full_text,
        chunk.start.char_offset,
        chunk.end.char_offset,
    )
    chunk_text = _augment_chunk_text(chunk.text, section_title)
    table.declare_row(
        row=DocChunk(
            id=await id_gen.next_id(chunk_text),
            source_path=str(source_path),
            file_type=file_type,
            chunk_start=chunk.start.char_offset,
            chunk_end=chunk.end.char_offset,
            text=chunk_text,
            chunk_hash=_chunk_hash(chunk_text),
            section_title=section_title,
            page_number=_page_number_for_offset(page_starts, chunk.start.char_offset),
            model_name=EMBED_CONFIG.model_name_for_storage,
            embedding=await embedder.embed(chunk_text),
        ),
    )


@coco.fn(memo=True)
async def process_file(
    file: FileLike,
    table: postgres.TableTarget[DocChunk],
) -> None:
    ext = pathlib.PurePath(file.file_path.path).suffix.lower()
    raw = await file.read()
    pages = _file_to_pages(raw, ext)
    text = "\n\n".join(pages)
    starts = _page_starts(pages)
    chunks = _splitter.split(text, chunk_size=800, chunk_overlap=120, language=_split_lang(ext))
    id_gen = IdGenerator()
    await coco.map(process_chunk, chunks, file.file_path.path, ext, text, starts, id_gen, table)


@coco.fn
async def app_main(sourcedir: pathlib.Path) -> None:
    target_table = await postgres.mount_table_target(
        PG_DB,
        table_name=TABLE_NAME,
        table_schema=await postgres.TableSchema.from_class(DocChunk, primary_key=["id"]),
        pg_schema_name=PG_SCHEMA,
    )
    files = localfs.walk_dir(
        sourcedir,
        recursive=True,
        path_matcher=build_path_matcher(),
        live=True,
    )
    await coco.mount_each(process_file, files.items(), target_table)


app = coco.App(
    coco.AppConfig(name="RagDocsIndex"),
    app_main,
    sourcedir=DOCS_DIR,
)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    mode = sys.argv[1] if len(sys.argv) > 1 else "update"
    if mode == "update":
        app.update_blocking(report_to_stdout=True)
    elif mode == "live":
        app.update_blocking(live=True, report_to_stdout=True)
    elif mode == "drop":
        app.drop_blocking()
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)
