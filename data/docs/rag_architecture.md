# RAG Architecture: Strategy B

Hệ thống RAG này dùng 2 pipeline song song để tách concern.

## Pipeline 1: Cocoindex → pgvector

Xử lý embedding vector cho semantic search. Re-indexable nhờ hash-of-code invalidation.

## Pipeline 2: Graphify → graph.json

Xây knowledge graph từ cùng source documents. Cập nhật incremental qua SHA256 cache.

## Hybrid Retrieval

Query time, retrieval service gọi cả 2 nguồn:
- pgvector cho semantic top-K
- graph traversal cho entity neighborhood

Reconciliation qua shared doc_id = sha256(path) + mtime. Drift window được monitor.
