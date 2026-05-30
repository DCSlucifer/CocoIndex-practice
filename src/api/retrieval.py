"""FastAPI service: hybrid retrieval = pgvector + graphify graph.json."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any

import psycopg
from fastapi import FastAPI
from fastapi.responses import FileResponse
from psycopg_pool import ConnectionPool
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from embedding_config import OpenAIEmbeddingClient, embedding_config_from_env
from .answering import Citation, DEFAULT_ANSWER_MODEL, generate_answer
from .graph_retrieval import GraphIndex
from .rerank import RetrievalCandidate, dedupe_candidates, rule_rerank


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GRAPH_PATH = PROJECT_ROOT / "data" / "docs" / "graphify-out" / "graph.json"
DEMO_HTML_PATH = Path(__file__).resolve().parent / "static" / "demo.html"
PG_CONN = os.getenv(
    "PG_CONN",
    "postgresql://postgres:ragpass@localhost:5433/ragdb",
)
EMBED_CONFIG = embedding_config_from_env()
EMBED_MODEL_NAME = EMBED_CONFIG.model_name_for_storage
ANSWER_MODEL = os.getenv("ANSWER_MODEL", DEFAULT_ANSWER_MODEL)
PG_POOL_MIN = int(os.getenv("PG_POOL_MIN", "1"))
PG_POOL_MAX = int(os.getenv("PG_POOL_MAX", "8"))

app = FastAPI(title="RAG Retrieval (Strategy B)")
_local_model = None
_openai_client = OpenAIEmbeddingClient(EMBED_CONFIG) if EMBED_CONFIG.provider == "openai" else None
_pool = ConnectionPool(conninfo=PG_CONN, min_size=PG_POOL_MIN, max_size=PG_POOL_MAX, open=True, timeout=10.0)

# Query embedding cache: hot queries hit cache.
# 1024 entries x ~1.5KB = ~1.5MB ceiling.
# /query runs _query_uncached in a threadpool, so these caches are read and
# mutated from multiple worker threads concurrently. The locks below keep the
# dict mutation + eviction atomic; without them a concurrent insert during
# `next(iter(...))` eviction can raise "dictionary changed size during iteration".
_EMBED_CACHE_MAX = 1024
_embed_cache: dict[str, list[float]] = {}
_embed_cache_hits = 0
_embed_cache_misses = 0
_embed_lock = threading.Lock()

_RESPONSE_CACHE_MAX = 512
_response_cache: dict[tuple[str, int, int, str, float], dict[str, Any]] = {}
_response_cache_hits = 0
_response_cache_misses = 0
_response_lock = threading.Lock()


def _embed_query(text: str) -> list[float]:
    global _embed_cache_hits, _embed_cache_misses, _local_model
    with _embed_lock:
        cached = _embed_cache.get(text)
        if cached is not None:
            _embed_cache_hits += 1
            return cached
        _embed_cache_misses += 1
    # Embedding (network call or model inference) is slow: compute outside the
    # lock so concurrent queries are not serialized on it.
    if EMBED_CONFIG.provider == "openai":
        if _openai_client is None:
            raise RuntimeError("OpenAI embedding client was not initialized")
        vec = _openai_client.embed_sync(text).tolist()
    else:
        if _local_model is None:
            from sentence_transformers import SentenceTransformer

            _local_model = SentenceTransformer(EMBED_CONFIG.model)
        vec = _local_model.encode([text], normalize_embeddings=True)[0].tolist()
    with _embed_lock:
        if text not in _embed_cache:
            if len(_embed_cache) >= _EMBED_CACHE_MAX:
                _embed_cache.pop(next(iter(_embed_cache)))
            _embed_cache[text] = vec
    return vec


def _model_dump(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


graph = GraphIndex(GRAPH_PATH)


class QueryRequest(BaseModel):
    question: str
    top_k: int = 5
    graph_depth: int = 1


class AnswerRequest(BaseModel):
    question: str
    top_k: int = 5
    graph_depth: int = 1


class ChunkHit(BaseModel):
    source_path: str
    chunk_text: str
    score: float
    vector_score: float
    rerank_score: float
    chunk_hash: str | None = None
    section_title: str | None = None
    page_number: int | None = None
    # True  -> graph corroborates this source doc (it appears in graph.json)
    # False -> source doc is outside the graph's coverage (e.g. PDFs, which
    #          Graphify does not ingest) — still a valid vector hit, NOT dropped
    # None  -> graph has no known corpus, so no cross-check was possible
    graph_known: bool | None = None


class GraphHit(BaseModel):
    node: dict
    distance: int = 1
    relation: str | None = None
    confidence: str | None = None
    confidence_score: float | None = None
    source_file: str | None = None
    source_location: str | None = None
    seed: str | None = None


class HybridResponse(BaseModel):
    vector_hits: list[ChunkHit]
    graph_hits: list[GraphHit]
    # True when a non-empty graph corpus was available, so each vector hit was
    # cross-checked against it (see ChunkHit.graph_known). Non-destructive: no
    # hit is removed, this only signals that the corroboration check ran.
    graph_known_doc_filter_applied: bool
    timing_ms: dict
    cached: bool = False


class AnswerResponse(BaseModel):
    question: str
    answer: str
    citations: list[Citation]
    vector_hits: list[ChunkHit]
    graph_hits: list[GraphHit]
    timing_ms: dict
    model: str
    retrieval_model: str
    cached: bool = False


@app.get("/demo")
def demo() -> FileResponse:
    return FileResponse(DEMO_HTML_PATH)


def _db_embedding_info() -> dict[str, Any]:
    """Read the vector dimensions + model_name actually stored in the DB.

    Used by /health to detect index/config drift: if the configured embedding
    model was changed but the index was not rebuilt, queries fail at runtime
    with "different vector dimensions". Surfacing it here turns a late 500 into
    an early, actionable health warning.
    """
    try:
        with _pool.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT DISTINCT vector_dims(embedding) FROM rag.doc_chunks")
            dims = sorted(r[0] for r in cur.fetchall())
            cur.execute("SELECT DISTINCT model_name FROM rag.doc_chunks")
            models = sorted(r[0] for r in cur.fetchall() if r[0])
        return {"dims": dims, "models": models, "error": None}
    except Exception as exc:  # table missing, DB down, etc. — never crash /health
        return {"dims": [], "models": [], "error": str(exc)}


@app.get("/health")
def health() -> dict[str, Any]:
    db = _db_embedding_info()
    configured_dim = EMBED_CONFIG.dimensions
    index_ready: bool | None = None
    warnings: list[str] = []
    if db["error"] is not None:
        warnings.append(f"Could not read index from DB: {db['error']}")
    elif not db["dims"]:
        warnings.append("Vector index is empty. Run: indexing.flow update")
    else:
        index_ready = db["dims"] == [configured_dim]
        if index_ready is False:
            warnings.append(
                f"Index dimension mismatch: DB has {db['dims']} but config is {configured_dim}. "
                f"Reindex: indexing.flow drop + update (DB models={db['models']})."
            )
    return {
        "ok": True,
        "index_ready": index_ready,
        "warnings": warnings,
        "model": EMBED_MODEL_NAME,
        "answer_model": ANSWER_MODEL,
        "embedding_provider": EMBED_CONFIG.provider,
        "embedding_dimensions": EMBED_CONFIG.dimensions,
        "db_embedding_dimensions": db["dims"],
        "db_model_names": db["models"],
        "graph_nodes": len(graph.nodes),
        "graph_mtime": graph.mtime,
        "pg_pool": {
            "min_size": PG_POOL_MIN,
            "max_size": PG_POOL_MAX,
        },
        "embed_cache": {
            "size": len(_embed_cache),
            "hits": _embed_cache_hits,
            "misses": _embed_cache_misses,
            "hit_rate": _embed_cache_hits / max(1, _embed_cache_hits + _embed_cache_misses),
        },
        "response_cache": {
            "size": len(_response_cache),
            "hits": _response_cache_hits,
            "misses": _response_cache_misses,
            "hit_rate": _response_cache_hits / max(1, _response_cache_hits + _response_cache_misses),
        },
    }


@app.post("/query", response_model=HybridResponse)
async def query(req: QueryRequest) -> HybridResponse:
    global _response_cache_hits, _response_cache_misses
    graph.maybe_reload()
    cache_key = (req.question, req.top_k, req.graph_depth, EMBED_MODEL_NAME, graph.mtime)
    with _response_lock:
        cached = _response_cache.get(cache_key)
        if cached is not None:
            _response_cache_hits += 1
        else:
            _response_cache_misses += 1
    if cached is not None:
        payload = dict(cached)
        payload["timing_ms"] = {"cache_ms": 0.0}
        payload["cached"] = True
        return HybridResponse(**payload)
    return await run_in_threadpool(_query_uncached, req, cache_key)


@app.post("/answer", response_model=AnswerResponse)
async def answer(req: AnswerRequest) -> AnswerResponse:
    t_total = time.perf_counter()
    retrieval = await query(
        QueryRequest(
            question=req.question,
            top_k=req.top_k,
            graph_depth=req.graph_depth,
        )
    )

    t_answer = time.perf_counter()
    result = await generate_answer(
        question=req.question,
        vector_hits=retrieval.vector_hits,
        graph_hits=retrieval.graph_hits,
        api_key=EMBED_CONFIG.api_key,
        base_url=EMBED_CONFIG.base_url,
        model=ANSWER_MODEL,
        organization=EMBED_CONFIG.organization,
        project=EMBED_CONFIG.project,
        timeout_seconds=EMBED_CONFIG.timeout_seconds,
        max_retries=EMBED_CONFIG.max_retries,
    )
    timings = dict(retrieval.timing_ms)
    timings["answer_ms"] = (time.perf_counter() - t_answer) * 1000
    timings["total_ms"] = (time.perf_counter() - t_total) * 1000

    return AnswerResponse(
        question=req.question,
        answer=result.answer,
        citations=result.citations,
        vector_hits=retrieval.vector_hits,
        graph_hits=retrieval.graph_hits,
        timing_ms=timings,
        model=result.model,
        retrieval_model=EMBED_MODEL_NAME,
        cached=retrieval.cached,
    )


def _query_uncached(
    req: QueryRequest,
    cache_key: tuple[str, int, int, str, float],
) -> HybridResponse:
    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    qvec = _embed_query(req.question)
    qvec_str = "[" + ",".join(f"{x:.6f}" for x in qvec) + "]"
    timings["embed_ms"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    with _pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                source_path,
                text,
                1 - (embedding <=> %s::vector) AS score,
                chunk_hash,
                section_title,
                page_number
            FROM rag.doc_chunks
            WHERE source_path NOT LIKE %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (qvec_str, "%graphify-out%", qvec_str, req.top_k * 8),
        )
        raw_candidates = [
            RetrievalCandidate(
                source_path=r[0],
                text=r[1],
                vector_score=float(r[2]),
                chunk_hash=r[3],
                section_title=r[4],
                page_number=r[5],
            )
            for r in cur.fetchall()
        ]
        candidates = rule_rerank(req.question, dedupe_candidates(raw_candidates))
        # Cross-validate each vector hit against the graph corpus. This is a
        # non-destructive annotation, NOT a filter: docs Graphify does not
        # ingest (e.g. PDFs) are kept so long-PDF evidence is never dropped.
        graph_corpus_known = bool(graph.known_source_files)
        vector_hits = [
            ChunkHit(
                source_path=candidate.source_path,
                chunk_text=candidate.text,
                score=candidate.vector_score,
                vector_score=candidate.vector_score,
                rerank_score=(
                    candidate.rerank_score
                    if candidate.rerank_score is not None
                    else candidate.vector_score
                ),
                chunk_hash=candidate.chunk_hash,
                section_title=candidate.section_title,
                page_number=candidate.page_number,
                graph_known=(
                    graph.is_graph_known_source(candidate.source_path)
                    if graph_corpus_known
                    else None
                ),
            )
            for candidate in candidates[: req.top_k]
        ]
    timings["pg_ms"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    context_texts = [hit.chunk_text for hit in vector_hits]
    graph_hits = [
        GraphHit(
            node=hit.node,
            distance=hit.distance,
            relation=hit.relation,
            confidence=hit.confidence,
            confidence_score=hit.confidence_score,
            source_file=hit.source_file,
            source_location=hit.source_location,
            seed=hit.seed,
        )
        for hit in graph.expand_for_query(
            req.question,
            context_texts=context_texts,
            top_k=req.top_k * 2,
            depth=req.graph_depth,
        )
    ]
    timings["graph_ms"] = (time.perf_counter() - t0) * 1000

    response = HybridResponse(
        vector_hits=vector_hits,
        graph_hits=graph_hits,
        graph_known_doc_filter_applied=graph_corpus_known,
        timing_ms=timings,
    )
    with _response_lock:
        if cache_key not in _response_cache:
            if len(_response_cache) >= _RESPONSE_CACHE_MAX:
                _response_cache.pop(next(iter(_response_cache)))
            _response_cache[cache_key] = _model_dump(response)
    return response
