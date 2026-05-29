# Spec: RAG có thể reindex + Knowledge Graph

**Ngày**: 2026-05-28
**Stack chốt**: Strategy B (2 pipeline song song)

## Yêu cầu

1. RAG re-indexable khi đổi embedding model.
2. Dùng graphify (tool, không reimplement) để build knowledge graph tăng accuracy.
3. Scale nhiều CCU.

## Quyết định kiến trúc: Strategy B

Hai pipeline song song trên cùng filesystem:

```
docs/  ─┬─►  cocoindex App  ─►  pgvector (Postgres)
        │      @coco.fn(memo=True) embed_text
        │      hash(code) đổi → auto reindex
        │
        └─►  graphify --watch ─►  graph.json + Neo4j (optional)
```

Retrieval service (FastAPI) join 2 nguồn ở query time.

## 3 fact rắn justify Strategy B

1. User yêu cầu "dùng graphify" → A reimplement graphify, trái yêu cầu.
2. Graph extraction không đụng embedding model → A buộc rerun graph khi đổi embed = lãng phí LLM extraction.
3. C đặt graphify (batch) thượng nguồn cocoindex (streaming) → mất sub-second freshness của cocoindex.

## Mitigations cho yếu điểm B (drift consistency)

- Shared `doc_id = sha256(path)[:16] + "_" + mtime_epoch` cho cả 2 pipeline.
- Query-time filter: `WHERE doc_id IN (graph_known_docs)`.
- Cron weekly full rebuild.
- Metric `staleness_ratio = |vector_ids △ graph_ids| / total`, alert > 5%.
- Verify drift window thật khi demo Step 2; nếu > 1 phút stable → fallback Strategy A.

## Reindex flow khi đổi embedding model

1. Add column `embedding_v2 vector(N)` vào table (online).
2. Sửa `embed_text()` → trỏ model mới.
3. Cocoindex hash đổi → backfill `embedding_v2` cho 100% rows trong nền.
4. Shadow A/B compare → drop `embedding_v1`.

## Hybrid retrieval (tăng accuracy)

1. `embed(query)` → top-K vector từ pgvector.
2. Lấy top entity từ chunks, expand neighborhood trong graph (graphify MCP `get_neighbors`).
3. Cross-encoder rerank.
4. Build context kèm `[node_id, confidence_tag]` → LLM giảm hallucinate.

## Scale CCU phân tầng

- 10-100 CCU: 1 box, Postgres+Neo4j+FastAPI cùng máy.
- 100-1.000 CCU: 4 FastAPI replica, Postgres primary + 2 read replica, Redis cache.
- 1.000-10.000 CCU: Qdrant cluster (3 node), Neo4j read replicas (hoặc Kuzu), LLM proxy có semantic cache.
- >10.000 CCU: dedicated retrieval service (Rust/Go), partition graph theo domain.

## Stack mặc định Step 2 demo

- Python 3.11+
- cocoindex (PyPI) → pgvector
- graphifyy (PyPI) → graph.json (Neo4j optional)
- FastAPI + uvicorn
- Embedding default updated to `text-embedding-3-large` (OpenAI, 3072d) for best-quality retrieval; local fallback remains `sentence-transformers/all-MiniLM-L6-v2` (384d).
- LLM: Claude/GPT API (mock answer nếu không có key)
- Postgres 16 + pgvector (Docker hoặc local)

## TODO Step 2 (verify thực nghiệm)

- [x] Đo drift window cocoindex vs graphify: 5.46s worst-case batch mode.
- [x] Demo reindex bằng cách đổi embedding model trong `EMBED_MODEL`; current production-quality path is `EMBED_PROVIDER=openai`, `EMBED_MODEL=text-embedding-3-large`, `EMBED_DIMENSIONS=3072`.
- [x] Test với ≥ 3 loại tài liệu: PDF, Markdown, code.
- [x] Q&A evidence eval: vector-only score 1.0 vs hybrid evidence score 3.0 trên 5 curated cases.

## TODO Step 3

- [x] Load test: 1 → 10 → 50 → 100 → 500 CCU concurrent.
- [x] Đo p50/p95/p99 latency.
- [x] Tối ưu bottleneck thật từ measurement: thêm response cache, async cache-hit path, cấu hình pool; kết luận single-process không đủ cho 500 CCU.

## Final Report

Xem báo cáo tổng kết và bài học tại `docs/reports/2026-05-28-rag-graphify-cocoindex-final-report.md`.
