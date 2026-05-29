# Cocoindex — Tài liệu nghiên cứu nội bộ

> Nguồn: tổng hợp từ repo gốc https://github.com/cocoindex-io/cocoindex (Apache 2.0, ~10k stars, v1.0.6 — 5/2026).
> Mục đích: hiểu cocoindex đủ sâu để quyết định kiến trúc cho hệ thống RAG + knowledge graph nội bộ (đi kèm `graphify`).

## 1. Cocoindex là gì (TL;DR)

Cocoindex là **framework Python để xây dataflow pipeline incremental cho AI/RAG**, với core engine viết bằng **Rust** (binding qua PyO3) và state store dùng **LMDB**. Triết lý: bạn khai báo `Target = F(Source)` theo kiểu declarative (như React khai báo UI = f(state)), còn engine sẽ tự lo việc detect thay đổi ở source và chỉ re-process đúng phần delta (Δ) cần thiết — không reprocess toàn bộ corpus.

## 2. Bài toán cốt lõi mà nó giải quyết

**Pain point của RAG/data pipeline truyền thống:**

- Pipeline batch (LangChain/LlamaIndex thuần) tái index theo cron → dữ liệu **stale**, agent trả lời sai vì context cũ.
- Khi corpus lên cỡ TB/PB, **re-embed toàn bộ tốn cực kỳ nhiều tiền** (mỗi lần đổi 1 file vẫn re-embed hết).
- Khi điều tra "tại sao agent ra câu này", không trace được vector đó sinh từ source nào — **không có lineage**.
- Caching custom phức tạp, dễ stale vì không biết khi nào code transform thay đổi.

**Cách cocoindex giải:**

1. **Incremental delta-only:** chỉ reprocess những row/file có hash khác lần trước → reduce cost ~10× theo claim của họ.
2. **Lineage 100%:** mỗi target row trace ngược về exact source byte → audit-friendly, debuggable.
3. **Code-aware memoization:** fingerprint = hash(input) + hash(bytecode function) → đổi code → invalidate đúng phần liên quan.
4. **Sub-second freshness:** live mode watch file → push delta ngay.

→ Nó nằm ở **data infrastructure layer** (dưới), bổ sung chứ không cạnh tranh với LangChain/LlamaIndex (orchestration layer, trên).

## 3. Use case cụ thể (chọn lọc từ folder `examples/` của repo)

| Use case | Mô tả ngắn | Path trong repo |
|---|---|---|
| PDF embedding cho RAG | PDF → text → chunk → embed → pgvector. Sửa 1 PDF chỉ re-embed file đó | `examples/pdf_embedding/` |
| Code embedding | Git repo → AST-aware chunk → embed code → semantic search cho coding agent | `examples/code_embedding/` |
| Podcast → Knowledge Graph | YouTube → Whisper transcribe → LLM extract speaker/statement → resolve entity → Neo4j/SurrealDB | `examples/conversation_to_knowledge/` |
| Meeting notes → KG | Notes Markdown → LLM extract Meeting/Person/Task → entity resolution → Neo4j | `examples/meeting_notes_graph_neo4j/` |
| Hacker News trending | Algolia API → fetch thread → LLM extract topic → rank → Postgres | `examples/hn_trending_topics/` |
| Multi-repo summary | N repo → README → LLM summarize → rollup org-level | `examples/multi_codebase_summarization/` |
| Structured extraction | Form/PDF/invoice → BAML/DSPy schema extract → warehouse | `examples/patient_intake_extraction_baml/` |
| CSV → Kafka live | Folder CSV → parse → publish per-row JSON Kafka, sub-second | `examples/csv_to_kafka/` |
| Google Drive embed | GDrive walk → embed → LanceDB, live | `examples/gdrive_text_embedding/` |
| Image search ColPali | Image → ColPali multimodal embed → LanceDB | `examples/image_search_colpali/` |

→ **Bài toán RAG + KG của project hiện tại** rơi đúng vào 2 example `pdf_embedding` (cho RAG vector) và `meeting_notes_graph_neo4j` (cho KG) — có thể nối chung 1 flow.

## 4. Triết lý thiết kế cần nắm (4 properties)

Trích từ `AGENTS.md` của repo:

1. **Python, not a DAG** — viết function async bình thường, không cần code DAG/operator boilerplate.
2. **Declare target state** — bạn nói "vector store này phải chứa X dạng Y", engine tự lo cách sync.
3. **Lineage end-to-end** — output → source byte trace được hết.
4. **Incremental at any scale** — từ 1 file đến PB, chỉ chạy Δ.

Mental model quan trọng:

- **Persistent-state-driven dataflow:** engine nhớ state cũ, so sánh, chỉ chạy thay đổi.
- **Component-path stability** (giống React `key`): cocoindex track component qua các lần chạy bằng stable path.
- **`@coco.fn(memo=True)`:** cache theo `hash(input) + hash(code)` — đổi 1 dòng code transform thì cache invalidate đúng phần đó.

## 5. Building blocks API (cheat sheet)

| API | Vai trò |
|---|---|
| `@coco.fn(memo=True)` | Khai báo 1 async transform được auto-memoize |
| `@coco.lifespan` | Khai báo dependency setup (DB pool, model) chạy 1 lần / vòng đời app |
| `DataScope`, `DataSlice` | Phạm vi dữ liệu được mount + slice (file path, offset, metadata) |
| `localfs.walk_dir(..., live=True)` | Source: file system, có live watch |
| `google_drive.walk_folder()`, `amazon_s3.walk_bucket()`, `postgres.read_table()` | Source connector khác |
| `RecursiveSplitter`, `SentenceTransformerEmbedder`, `detect_code_language`, `resolve_entities` | Built-in transform thường dùng |
| `postgres.mount_table_target(...)` + `.declare_vector_index(column="embedding")` | Sink: Postgres + pgvector |
| `neo4j.mount_graph_target(...)`, `.declare_record(Node)`, `.declare_relation(Edge)` | Sink: Neo4j KG (Kuzu/FalkorDB tương tự) |
| `qdrant.mount_target`, `lancedb.mount_target`, `kafka.mount_topic_target` | Các sink khác |
| `coco.map(fn, items, ...)`, `coco.mount_each(...)` | Parallel map / mount per item |
| CLI: `cocoindex update main` | Backfill 1 lần |
| CLI: `cocoindex update -L main` | Live mode (stream delta) |
| CLI: `cocoindex server` | API server |

## 6. Code mẫu tối thiểu (text embedding)

Rút gọn từ `examples/text_embedding/main.py` của repo:

```python
import asyncpg, cocoindex as coco
from cocoindex.connectors import localfs, postgres
from cocoindex.functions import SentenceTransformerEmbedder, RecursiveSplitter

PG_DB = coco.ContextKey("pg_db")
EMBEDDER = coco.ContextKey("embedder")

@coco.lifespan
async def lifespan(builder):
    async with asyncpg.create_pool(DATABASE_URL) as pool:
        builder.provide(PG_DB, pool)
        builder.provide(EMBEDDER, SentenceTransformerEmbedder("all-MiniLM-L6-v2"))
        yield

@coco.fn(memo=True)
async def process_file(file, table):
    text = await file.read_text()
    chunks = RecursiveSplitter(chunk_size=2000, overlap=500).split(text)
    embedder = coco.use_context(EMBEDDER)
    for chunk in chunks:
        vec = await embedder.embed(chunk.text)
        table.declare_row(DocEmbedding(path=file.path, text=chunk.text, embedding=vec))

@coco.fn
async def app_main(sourcedir):
    table = await postgres.mount_table_target(PG_DB, "doc_embeddings",
                                              table_schema=TableSchema.from_class(DocEmbedding))
    table.declare_vector_index(column="embedding")
    files = localfs.walk_dir(sourcedir,
                             path_matcher=PatternFilePathMatcher(included_patterns=["**/*.md"]),
                             live=True)
    await coco.mount_each(process_file, files.items(), table)

app = coco.App(coco.AppConfig(name="TextEmbedding"), app_main, sourcedir=Path("./docs"))
```

Chạy: `cocoindex update -L main` → live watch folder `docs/`, sửa 1 file `.md` thì engine chỉ re-embed file đó.

## 7. Tích hợp Knowledge Graph (Neo4j) — quan trọng với project

Pattern chuẩn (rút từ `examples/meeting_notes_graph_neo4j/main.py`):

```python
@dataclass
class Person:  name: str  # canonical
@dataclass
class Meeting: id: int; note_file: str; time: datetime.date

@coco.fn
async def extract_meeting(section_text: str) -> ExtractedMeeting:
    # instructor + litellm => Pydantic schema
    ...

graph = await neo4j.mount_graph_target(KG_DB)
graph.declare_record(Meeting(...))           # node
graph.declare_relation(AttendedRel(...))     # edge

# Entity resolution: dedup tên người bằng embedding + LLM tie-break
resolved = await resolve_entities(raw_names, embedder=EMBEDDER,
                                  llm_resolver=LlmPairResolver(...))
for canonical in resolved:
    graph.declare_record(Person(name=canonical))
```

Đổi Kuzu/FalkorDB chỉ cần đổi connector — logic giữ nguyên. **Đây là chỗ ráp với `graphify`:** cocoindex lo extract + dedup + materialize node/edge sang Neo4j, `graphify` có thể làm layer trên (truy vấn KG, traversal, reasoning) — chứ không cần `graphify` tự cào dữ liệu.

## 8. Kiến trúc bên dưới (cần biết để debug)

- **Core engine:** Rust 100% tại `rust/core/src/`, binding qua PyO3 (`rust/py/`). Async runtime = Tokio.
- **State store:** LMDB (qua crate `heed`), per-environment. Default 4 GiB, 1024 sub-DBs. Có retry logic exponential backoff khi `MDB_READERS_FULL`.
- **Fingerprint:** Blake2b 16-byte, encode Base64 nếu human-readable (`rust/utils/src/fingerprint.rs`).
- **Provenance per-row:** key `StablePathEntryKey` lưu `FunctionMemoization(Fingerprint)` + `TrackingInfo` (source range) + `ChildExistence(StableKey)` → cho phép trace từ vector → byte source.
- **Live mode:** `LiveComponent` + `auto_refresh` channel-based; component path stability để match lại sau restart.
- **Atomic commit:** `submit_session.rs` (parallel-write shape), borrow-only reconcile.

## 9. Ưu điểm (có evidence)

- **Incremental thật:** không phải nhãn marketing — code có fingerprint + LMDB state + per-row provenance.
- **Lineage 100%:** rất hữu ích cho compliance / debug "vì sao agent nói X".
- **Rust core:** retry, batch, parallel write sẵn sàng production; latest commit `6aaded62` (27/05/2026) — repo active.
- **v1.0.6 stable**, cadence release đều (~hàng tháng từ v1.0.0 22/04/2026).
- **Hệ sinh thái connector rộng:** 15+ target (Postgres/pgvector, Qdrant, LanceDB, Neo4j, Kuzu, FalkorDB, SurrealDB, Kafka, Turbopuffer, Iggy, Doris, OCI, GDrive, S3, SQLite), 8+ source.
- **28+ examples** chạy được, cover hầu hết kịch bản RAG/KG thực tế.
- **Memoization built-in** với `memo=True` — không phải tự viết cache layer.

## 10. Nhược điểm / hạn chế (cần biết trước khi commit)

- **LMDB là single point of state:** không có built-in replication / multi-region. Backup phải tự lo. Có giới hạn `MDB_MAXREADERS` (default 126, tune được nhưng vẫn là single-process-ish).
- **Đường cong học:** mental model declarative + lineage + component path không phải ai cũng quen, dễ viết sai pattern dẫn đến memo không hit.
- **Doc còn mỏng so với LangChain/LlamaIndex** — issue #1553 đang migrate sang Zensical SSG. Một số connector mới chưa có guide riêng.
- **Vendor connector chưa có Pinecone, Elasticsearch target;** Slack source hạn chế (không rich thread traversal).
- **CLI đang nợ kỹ thuật:** issue #1554 migrate Click → Typer.
- **Một số mảng KG còn thô:** Neo4j batching (#1431), null PK (#1430), LanceDB index optim (#1352, #1435).
- **Phụ thuộc Postgres mạnh** cho nhiều example (pgvector) — không bắt buộc nhưng default examples đi theo, dễ tưởng là yêu cầu.
- **Còn trẻ:** v1.0.x mới ra ~1 tháng tính tới 29/05/2026 → ổn định ở mức "stable nhưng còn vá nhanh"; chấp nhận bump version định kỳ.

## 11. So sánh nhanh với LangChain / LlamaIndex

| Mục | Cocoindex | LangChain | LlamaIndex |
|---|---|---|---|
| Layer | Data infra (indexing/ETL) | Orchestration (chain/agent) | Index + retriever |
| Lập trình | Declarative + Rust core | Imperative chain | Declarative index, mature retriever |
| Incremental | Per-row fingerprint + LMDB | Không có native | Document-level versioning sơ khai |
| Lineage | 100% byte → vector | Manual log | Qua metadata |
| State | LMDB embedded | Tùy (Redis, SQL, memory) | Tùy vector DB |
| Phù hợp khi | Cần fresh + cheap reindex + audit | Cần orchestration agent | Cần retriever mạnh sẵn |

→ Không "thay thế" — combine: **cocoindex** lo dữ liệu vào KG/vector store luôn fresh, **LangChain/LlamaIndex/graphify** lo phần truy vấn/agent ở trên.

## 12. Recommend cho project RAG + KG hiện tại

- Dùng cocoindex làm lớp **ingest + reindex incremental**: source = docs/PDF/markdown; target = Postgres + pgvector (cho retrieval semantic) **và** Neo4j/Kuzu (cho KG).
- Pattern KG: copy `examples/meeting_notes_graph_neo4j` → đổi schema thành domain của project, dùng `resolve_entities` để dedup entity.
- Để `graphify` ngồi trên KG đã được cocoindex materialize → tránh trùng vai trò.
- Cẩn thận với LMDB: setup backup định kỳ thư mục state, đừng để chung disk với DB chính.
- Bám `@coco.fn(memo=True)` cho mọi transform tốn token LLM (extract entity, summarize) — đây là chỗ tiết kiệm cost nhiều nhất.

## 13. Tài liệu tham khảo

- Repo: https://github.com/cocoindex-io/cocoindex
- README chính + design philosophy: `README.md`, `AGENTS.md`
- Examples: `examples/` (28+ folder)
- Code core: `rust/core/src/`, `python/cocoindex/`
- Issues hiện hành: https://github.com/cocoindex-io/cocoindex/issues
- Release notes: https://github.com/cocoindex-io/cocoindex/releases
