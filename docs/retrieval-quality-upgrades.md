# Retrieval Quality Upgrades

Implemented upgrades:

- Chunk metadata in `rag.doc_chunks`:
  - `chunk_hash`
  - `section_title`
  - `page_number`
- Section-aware embedding text:
  - chunks with headings are embedded as `Section: <title>\n<chunk text>`
- Retrieval overfetch:
  - pgvector fetches `top_k * 8` candidates before post-processing
- Top-k dedupe:
  - exact duplicate chunks are collapsed by `chunk_hash`, with normalized text fallback
- Rule reranking:
  - vector score remains visible as `vector_score`
  - deterministic reranker adds section-title and token-overlap boosts as `rerank_score`
- Long PDF fixture:
  - no repeated full-section copies
  - test coverage asserts exact duplicate chunks are not present

Current status:

- This is stronger than raw vector-only retrieval and suitable for the POC.
- It is not a full cross-encoder reranker. For production, add a model-based
  reranker behind the same `api.rerank` boundary.

Latest long-PDF evidence:

- Total chunks: 15
- Long PDF chunks: 6
- Distinct chunk hashes: 15
- Duplicate chunk rows: 0
- Embedding model: `openai:text-embedding-3-large:3072`
- Shadow-index evidence rank: 1
- Scaling-considerations evidence rank: 1
