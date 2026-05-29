# Báo cáo kỹ thuật: Reindexable RAG với CocoIndex + Graphify

Ngày tạo POC: 2026-05-28
Cập nhật mới nhất: 2026-05-29
Workspace: `D:\Rag vsf`
API đang dùng khi verify: `http://127.0.0.1:8003`

## 1. Tóm tắt điều đã hoàn thành

Yêu cầu ban đầu:

1. Nghiên cứu `https://github.com/safishamsi/graphify`.
2. Nghiên cứu `https://github.com/cocoindex-io/cocoindex`.
3. Xây dựng kiến trúc RAG có thể reindex khi thay đổi embedding model.
4. Dùng Graphify xây dựng graph thông tin để tăng độ chính xác cho LLM.
5. Step 1: lên kiến trúc, giải thích framework, trình bày các strategy index một data vào database.
6. Tự debate kiến trúc có đáp ứng scale nhiều CCU không.
7. Step 2: demo thử với nhiều loại tài liệu.
8. Step 3: tối ưu lại, trình bày, giả lập tải hỏi đáp.

Kết luận hiện tại:

- Đã hoàn thành POC retrieval/evidence RAG theo kiến trúc hai pipeline: CocoIndex cho vector index, Graphify cho knowledge graph.
- Đã đổi embedding path sang OpenAI `text-embedding-3-large` với vector `3072` chiều.
- Đã reindex lại DB sau khi đổi embedding dimension.
- Đã bổ sung chunk metadata: `chunk_hash`, `section_title`, `page_number`.
- Đã thêm section-aware chunking, top-k dedupe, rule reranking.
- Đã cập nhật long PDF fixture để không còn lặp exact chunks.
- Đã verify retrieval trên nhiều loại tài liệu: Markdown, PDF, Python code.
- Đã có evaluation, long-PDF check, drift/load-test script, regression tests.
- Kiến trúc hiện tại là retrieval/evidence layer. Bước `HybridResponse -> LLM answer generator -> final answer with citations` chưa được implement trong API này, nhưng output đã đủ metadata để nối vào LLM.

## 2. Nguồn nghiên cứu framework

### 2.1. CocoIndex

Nguồn đã đối chiếu:

- GitHub: https://github.com/cocoindex-io/cocoindex
- README raw: https://raw.githubusercontent.com/cocoindex-io/cocoindex/main/README.md
- Docs: https://cocoindex.io/docs/

Các điểm chính rút ra:

- CocoIndex được mô tả là incremental engine cho AI agents/RAG, chỉ reprocess delta khi source hoặc transform thay đổi.
- Mental model là khai báo target state: source đi qua transformation, engine giữ target đồng bộ.
- README có pattern đọc file, split/chunk, embed, rồi upsert vào vector DB như pgvector/LanceDB.
- `@coco.fn(memo=True)` cache theo input và hash/code của function, phù hợp để tránh embed lại toàn bộ corpus khi không cần.
- CocoIndex phù hợp cho long-running context/index của agent vì có lineage, incremental recomputation, target sync.
- README cũng nêu các use case liên quan trực tiếp đến bài toán này: PDF to RAG index, code index, vector DB, conversation to knowledge graph.

Ý nghĩa với bài toán:

- CocoIndex là lựa chọn hợp lý cho vector indexing pipeline vì bài toán có yêu cầu reindex khi đổi embedding model.
- Khi đổi model hoặc logic embed, ta muốn pipeline tự xác định output nào bị ảnh hưởng và rebuild đúng phần cần rebuild.
- Với model đổi dimension, cần xử lý schema vector cẩn thận. POC hiện chọn drop/rebuild cho demo; production nên dùng shadow column/table.

### 2.2. Graphify

Nguồn đã đối chiếu:

- GitHub: https://github.com/safishamsi/graphify
- README raw: https://raw.githubusercontent.com/safishamsi/graphify/main/README.md

Các điểm chính rút ra:

- Graphify biến một folder code/docs/PDF/images/video thành queryable knowledge graph.
- Output chính gồm `graph.html`, `GRAPH_REPORT.md`, `graph.json`, `cache/`.
- `graph.json` là persistent graph để query lại mà không phải đọc raw files.
- `GRAPH_REPORT.md` nêu god nodes, surprising connections, suggested questions.
- `cache/` dùng SHA256 cache để chỉ reprocess file thay đổi.
- Graphify hỗ trợ `query`, `path`, `explain`, `--update`, `--watch`, `--wiki`, `--neo4j`, `--mcp`.
- Code được extract bằng AST/tree-sitter; docs/PDF/image có thể dùng model API/vision tùy extra.
- Edge có confidence tag như `EXTRACTED`, `INFERRED`, `AMBIGUOUS`, giúp phân biệt evidence tìm thấy trực tiếp với suy luận.

Ý nghĩa với bài toán:

- Graphify phù hợp để tạo graph evidence bổ sung cho vector search.
- Graph layer không thay thế vector retrieval; nó bổ sung structural context: node, relation, confidence, source.
- Graphify artifact là output sinh ra, không phải source corpus. Vì vậy `graphify-out/**` phải bị exclude khỏi vector index để tránh tự index report/graph output.

## 3. Chiến lược kiến trúc đã cân nhắc

| Strategy | Mô tả | Ưu điểm | Nhược điểm | Kết luận |
|---|---|---|---|---|
| A. CocoIndex làm cả vector và graph | Một pipeline xử lý chunk, embed, extract graph | Ít drift, một engine | Không đáp ứng đúng yêu cầu dùng Graphify; phải build lại phần graph extraction | Không chọn |
| B. Hai pipeline song song | CocoIndex quản lý vector index, Graphify quản lý graph; API join lúc query | Tách đúng responsibility; đổi embedding không cần rebuild graph | Có drift giữa vector index và graph | Chọn |
| C. Graphify trước, CocoIndex index artifact | Graphify tạo artifact, CocoIndex index artifact | Demo nhanh | Dễ index nhầm `GRAPH_REPORT.md`, làm bẩn corpus | Không chọn |

Kiến trúc đã chọn:

```text
data/docs
  |-- CocoIndex pipeline -> Postgres/pgvector -> vector retrieval
  `-- Graphify pipeline  -> graph.json        -> graph evidence

FastAPI /query
  question
  -> query embedding
  -> pgvector overfetch
  -> dedupe
  -> rule rerank
  -> graph expansion
  -> HybridResponse
```

Lý do chọn Strategy B:

- Embedding model change chủ yếu ảnh hưởng vector index, không nhất thiết ảnh hưởng graph topology.
- Graphify graph extraction có lifecycle riêng: update khi source docs/code thay đổi.
- CocoIndex mạnh ở target sync và incremental indexing.
- Graphify mạnh ở extraction graph và confidence-tagged relations.
- Tách pipeline giúp giảm blast radius: lỗi vector không phá graph, lỗi graph không phá vector DB.
- Nhược điểm drift được chấp nhận ở POC và cần metric/monitoring khi production.

## 4. Thiết kế RAG hiện tại

### 4.1. Layer tổng quát

```text
Input Layer
  - Documents and Code
  - User Question

Indexing Layer
  - Chunking and metadata
  - OpenAI embeddings
  - Graph extraction

Storage Layer
  - Postgres pgvector
  - graph.json

Retrieval Layer
  - FastAPI /query
  - Vector search
  - Dedupe and rerank
  - Graph evidence

Output Layer
  - Retrieved context
  - Hybrid evidence response
```

Figma diagrams:

- Detailed architecture: https://www.figma.com/board/lKAHjlnRCKCt39Wp3NjDM4
- Layered overview: cùng FigJam file ở trên.

### 4.2. End-to-end indexing flow

```text
data/docs
  -> localfs.walk_dir
  -> exclude graphify-out/**
  -> read file bytes
  -> PDF: pypdf extract pages
  -> MD/TXT/PY: utf-8 decode
  -> split chunks
  -> derive section_title
  -> derive page_number
  -> prepend section title into chunk text
  -> compute chunk_hash
  -> embed chunk with OpenAI text-embedding-3-large
  -> write row into rag.doc_chunks
```

File chính: `src/indexing/flow.py`

Các điểm đã implement:

- Source dir: `data/docs`.
- Included patterns: `.md`, `.txt`, `.py`, `.pdf`.
- Excluded patterns: `graphify-out/**`, `**/graphify-out/**`.
- PDF extraction: `pypdf`.
- Chunker: `RecursiveSplitter`.
- Chunk config hiện tại:
  - `chunk_size=800`
  - `chunk_overlap=120`
- Section-aware chunking:
  - detect heading dạng Markdown hoặc numbered heading.
  - prepend `Section: <section_title>` vào chunk text trước khi embed.
- Metadata lưu cùng row:
  - `chunk_hash`
  - `section_title`
  - `page_number`
  - `chunk_start`
  - `chunk_end`
  - `model_name`
- Embedding:
  - provider: `openai`
  - model: `text-embedding-3-large`
  - dimensions: `3072`
- Local fallback vẫn có:
  - `sentence-transformers/all-MiniLM-L6-v2`
  - dimensions `384`

Lý do prepend section title:

- Query thường hỏi theo chủ đề như "scaling considerations" hoặc "embedding migration".
- Nếu chunk chỉ chứa body text, heading có thể bị tách hoặc bị dilute.
- Prepend heading giúp embedding nhìn thấy section context, làm rank đúng section tốt hơn.

Lý do lưu `chunk_hash`:

- Corpus thật có thể lặp cùng đoạn ở nhiều trang hoặc phiên bản.
- Top-k dễ bị chiếm bởi duplicate.
- `chunk_hash` cho phép dedupe top-k ổn định hơn normalized text runtime.

Lý do lưu `page_number` và spans:

- Dùng cho citation.
- Dùng để debug retrieval.
- Dùng để trả evidence có vị trí nguồn rõ ràng cho LLM.

### 4.3. End-to-end graph flow

```text
data/docs
  -> graphify update / graphify extraction
  -> graphify-out/graph.json
  -> GraphIndex loads graph.json
  -> rank nodes by query/context tokens
  -> expand neighbor edges
  -> return graph evidence
```

Files/artifacts:

- `data/docs/graphify-out/graph.json`
- `data/docs/graphify-out/graph.html`
- `data/docs/graphify-out/GRAPH_REPORT.md`
- `src/api/graph_retrieval.py`

Current graph artifact evidence:

- Graph nodes: `41`
- Source files represented include:
  - `sample_code.py`
  - `cocoindex_intro.md`
  - `embedding_models.md`
  - `graphify_intro.md`
  - `rag_architecture.md`
  - `drift_test_doc.md`
- Confidence tags observed in graph/eval: `EXTRACTED`.

GraphIndex behavior:

- Tokenizes query and vector context.
- Normalizes terms such as `re-index` -> `reindex`.
- Ranks graph nodes by query overlap and context overlap.
- Expands neighbors up to `graph_depth`.
- Returns graph hits with:
  - `node`
  - `relation`
  - `confidence`
  - `confidence_score`
  - `source_file`
  - `source_location`
  - `seed`

### 4.4. End-to-end query flow

```text
User question
  -> FastAPI POST /query
  -> response cache lookup
  -> query embedding cache lookup
  -> OpenAI query embedding
  -> pgvector search, overfetch top_k * 8
  -> dedupe candidates
  -> rule rerank
  -> final vector_hits
  -> graph expansion using question + vector context
  -> HybridResponse
```

File chính:

- `src/api/retrieval.py`
- `src/api/rerank.py`
- `src/api/graph_retrieval.py`

Retrieval details:

- Query embedding dùng cùng provider/model/dimension với indexing.
- pgvector dùng cosine similarity:

```sql
1 - (embedding <=> query_vector) AS score
```

- API không lấy đúng `top_k` ngay, mà overfetch `top_k * 8`.
- Dedupe:
  - ưu tiên `chunk_hash`
  - fallback normalized text
- Rule rerank:
  - giữ `vector_score` gốc.
  - tạo `rerank_score`.
  - boost khi query token match `section_title`.
  - boost khi query token match chunk text.
  - boost nhỏ khi section phrase chứa query term.

Response `vector_hits` hiện có:

- `source_path`
- `chunk_text`
- `score`
- `vector_score`
- `rerank_score`
- `chunk_hash`
- `section_title`
- `page_number`

Response `graph_hits` hiện có:

- `node`
- `distance`
- `relation`
- `confidence`
- `confidence_score`
- `source_file`
- `source_location`
- `seed`

## 5. Reindex khi đổi embedding model

### 5.1. Thiết kế

Có hai trường hợp:

1. Same dimension model:
   - Có thể reindex in-place nếu schema vector dimension không đổi.
   - CocoIndex detect change qua embedder config/function code và rebuild affected rows.

2. Different dimension model:
   - Không nên update trực tiếp cột vector cũ.
   - Cần shadow column/table:

```text
embedding_v1 vector(384)
embedding_v2 vector(3072)
backfill embedding_v2
A/B compare
switch read path
drop embedding_v1 sau khi ổn định
```

Trong POC, để demo nhanh và an toàn với corpus nhỏ, đã dùng drop/rebuild:

```powershell
$env:EMBED_PROVIDER = "openai"
$env:EMBED_MODEL = "text-embedding-3-large"
$env:EMBED_DIMENSIONS = "3072"
$env:PYTHONPATH = "src"

.\.venv\Scripts\python.exe -m indexing.flow drop
.\.venv\Scripts\python.exe -m indexing.flow update
```

### 5.2. Kết quả hiện tại

Health check API:

```json
{
  "model": "openai:text-embedding-3-large:3072",
  "embedding_provider": "openai",
  "embedding_dimensions": 3072
}
```

DB smoke check mới nhất:

```text
total_chunks: 15
distinct_chunk_hashes: 15
duplicate_chunk_rows: 0
chunks_with_section_title: 11
chunks_with_page_number: 15
min vector dims: 3072
max vector dims: 3072
```

Bằng chứng:

- `docs/openai-embedding-3-large.md`
- `reports/long_pdf_retrieval_check.json`
- `src/embedding_config.py`
- `src/indexing/flow.py`

## 6. Demo nhiều loại tài liệu

Corpus hiện có trong `data/docs`:

| Loại | File ví dụ | Vai trò |
|---|---|---|
| Markdown | `cocoindex_intro.md`, `embedding_models.md`, `graphify_intro.md`, `rag_architecture.md`, `drift_test_doc.md` | Docs về framework, kiến trúc, drift |
| PDF ngắn | `rag_paper_intro.pdf` | Test PDF ingestion cơ bản |
| PDF dài | `rag_long_whitepaper.pdf` | Test long-form RAG retrieval, section/page metadata |
| Python code | `sample_code.py` | Test code/document graph extraction và vector retrieval |
| Graphify artifacts | `data/docs/graphify-out/**` | Output graph, bị exclude khỏi vector index |

Long PDF fixture hiện tại:

- Generator: `scripts/make_long_pdf.py`
- Không còn lặp nguyên section 3 lần như bản cũ.
- Test đảm bảo không có exact duplicate chunks.
- Nội dung gồm:
  - Problem Statement
  - CocoIndex Incremental Indexing
  - Embedding Model Migration
  - Graphify Knowledge Graph
  - Hybrid Retrieval
  - Drift Management
  - Scaling Considerations
  - Lessons Learned
  - Chunk Metadata
  - Reranking and Deduplication
  - Evaluation Strategy
  - Deployment Checklist

## 7. Tối ưu retrieval đã làm ở Step 3

### 7.1. Vấn đề trước tối ưu

Các vấn đề đã quan sát:

- `best_score` không cao dù source đúng.
- Long PDF fixture cũ lặp exact chunks, làm top-k bị duplicate chiếm chỗ.
- Query "scaling considerations" có lúc rank intro chunk cao hơn section scaling.
- Metadata cho citation/debug còn thiếu.
- Chưa có reranking sau vector search.

### 7.2. Tối ưu đã triển khai

File chính:

- `src/api/rerank.py`
- `src/api/retrieval.py`
- `src/indexing/flow.py`
- `tests/test_rerank.py`
- `tests/test_long_pdf_ingestion.py`

Đã làm:

1. Section-aware embedding text:

```text
Section: 7. Scaling Considerations
7. Scaling Considerations ...
```

2. Chunk metadata:

```text
chunk_hash
section_title
page_number
chunk_start
chunk_end
```

3. Dedupe:

```text
raw vector candidates
  -> dedupe by chunk_hash
  -> fallback normalized text
```

4. Rule rerank:

```text
rerank_score =
  vector_score
  + section overlap boost
  + text token overlap boost
  + section phrase bonus
```

5. Overfetch:

```text
pgvector LIMIT = top_k * 8
```

6. Long PDF fixture fixed:

- No repeated full-section copies.
- Duplicate test added.

### 7.3. Bằng chứng tối ưu retrieval

File: `reports/long_pdf_retrieval_check.json`

DB evidence:

```text
total_chunks: 15
total_docs: 8
long_pdf_chunks: 6
distinct_chunk_hashes: 15
duplicate_chunk_rows: 0
chunks_with_section_title: 11
chunks_with_page_number: 15
embedding_model: openai:text-embedding-3-large:3072
embedding_dimensions: 3072
```

Case 1: shadow index / shadow column

```text
question: What does the long whitepaper say about shadow index or shadow column for embedding migration?
evidence_marker: Embedding Model Migration
best_vector_score: 0.515
best_rerank_score: 0.745
evidence_rank: 1
section_title: 3. Embedding Model Migration
page_number: 1
```

Case 2: scaling considerations

```text
question: What scaling considerations are described in the long-form RAG whitepaper?
evidence_marker: Scaling Considerations
best_vector_score: 0.525
best_rerank_score: 0.725
evidence_rank: 1
section_title: 7. Scaling Considerations
page_number: 2
```

Ý nghĩa:

- Vector score tuyệt đối vẫn khoảng 0.5 vì đây là cosine similarity raw, không phải xác suất đúng.
- Rerank score cao hơn vì section title match giúp hệ thống hiểu đúng intent.
- Evidence giờ đứng rank 1 ở cả hai case.
- Duplicate rows về 0, top-k không còn bị cùng một đoạn lặp chiếm chỗ.

## 8. Evaluation retrieval

File kết quả mới nhất: `reports/retrieval_eval_optimized.json`

Command:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe scripts\evaluate_retrieval.py --url http://127.0.0.1:8003/query --out reports\retrieval_eval_optimized.json
```

Summary mới nhất:

```json
{
  "cases": 5,
  "vector_source_recall": 1.0,
  "graph_evidence_recall": 1.0,
  "confidence_tag_recall": 1.0,
  "avg_vector_only_score": 1,
  "avg_hybrid_score": 3,
  "p50_latency_ms": 807.8719999994064,
  "max_latency_ms": 913.5178000005908
}
```

Các case:

1. `reindex_model_change`
2. `graphify_confidence`
3. `hybrid_code_path`
4. `incremental_processing`
5. `strategy_b`

Diễn giải:

- Vector source recall đạt 100% trên 5 curated cases.
- Graph evidence recall đạt 100%.
- Confidence tag recall đạt 100%.
- Latency hiện cao hơn bản local MiniLM cũ vì cold query phải gọi OpenAI embedding API bên ngoài.
- Khi response cache hit, latency sẽ thấp hơn nhiều; tuy nhiên production cần distributed cache thay vì in-memory cache.

## 9. Load test và scale debate

### 9.1. Load test đã có

Script: `scripts/load_test.py`

Command từng dùng:

```powershell
.\.venv\Scripts\python.exe scripts\load_test.py --url http://127.0.0.1:8003/query --levels 1,10,50,100,500 --reqs 5
```

Kết quả local optimized historical:

| CCU | Requests | Errors | p50 | p95 | p99 | QPS |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 5 | 0 | 4.3 ms | 4.9 ms | 4.9 ms | 229.2 |
| 10 | 50 | 0 | 33.1 ms | 144.4 ms | 163.7 ms | 185.6 |
| 50 | 250 | 0 | 227.5 ms | 988.3 ms | 1421.8 ms | 113.7 |
| 100 | 500 | 0 | 468.8 ms | 2246.1 ms | 3164.2 ms | 102.2 |
| 500 | 2500 | 0 | 1620.0 ms | 17504.7 ms | 20011.9 ms | 114.6 |

Lưu ý:

- Bảng trên là bằng chứng local POC/cache behavior trước khi chuyển toàn bộ sang OpenAI embedding large.
- Sau khi dùng OpenAI embedding, cold query latency bị chi phối bởi network/API embedding.
- Không tự chạy lại 500 CCU bằng OpenAI trong lần cập nhật này để tránh đốt API quota không cần thiết.
- Với production thật, cần benchmark riêng theo quota, rate limit, region, cache hit rate và traffic shape thực tế.

### 9.2. Tự debate scale nhiều CCU

Lập luận ủng hộ:

- Strategy B tách vector indexing và graph extraction, giảm blast radius.
- Query path có response cache và query embedding cache.
- Postgres connection pool có `PG_POOL_MIN`, `PG_POOL_MAX`.
- Retrieval có thể scale ngang bằng nhiều API replicas nếu dùng shared cache.
- Graph artifact có thể load memory per replica, query nhanh với corpus vừa/nhỏ.

Lập luận phản biện:

- Current API là single-process local service.
- In-memory cache không dùng chung giữa replicas.
- OpenAI embedding API là external bottleneck/rate limit.
- pgvector trên Postgres cần HNSW/IVFFlat tuning khi corpus lớn.
- Graphify và CocoIndex là hai pipeline độc lập, có consistency drift.
- Graph artifact `graph.json` phù hợp POC; graph lớn production nên cân nhắc Neo4j/Kuzu hoặc graph snapshot/versioning.

Kết luận scale:

- Kiến trúc đúng hướng cho POC và có path lên production.
- Bản hiện tại chưa đủ cho high CCU production.
- Để production cần:
  - API replicas sau load balancer.
  - Redis exact cache + semantic cache.
  - Shared response/query embedding cache.
  - pgvector HNSW/IVFFlat hoặc Qdrant/Milvus nếu corpus lớn.
  - Rate limit/backoff cho OpenAI embeddings.
  - Async ingestion workers.
  - Drift metric giữa vector corpus và graph corpus.
  - Observability p50/p95/p99, cache hit rate, evidence rank, duplicate rate.
  - Cross-encoder reranker nếu cần ranking mạnh hơn rule reranker.

## 10. Drift và consistency

Script: `scripts/drift_test.py`

Kết quả historical:

```text
CocoIndex incremental: 6.22s
Graphify incremental: 0.76s
Drift window: 5.46s
```

Diễn giải:

- Strategy B có drift thật vì vector pipeline và graph pipeline chạy độc lập.
- Drift chấp nhận được trong POC vì corpus nhỏ và retrieval vẫn hoạt động nếu graph chưa có document mới.
- Production cần đo:

```text
vector_known_doc_ids
graph_known_doc_ids
drift = symmetric_difference(vector_known_doc_ids, graph_known_doc_ids)
```

Nếu drift vượt ngưỡng:

- cảnh báo,
- degrade graph evidence,
- hoặc chỉ dùng vector retrieval cho document mới.

## 11. Verification hiện tại

### 11.1. Unit tests

Command:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Kết quả mới nhất sau khi cập nhật report:

```text
Ran 16 tests in 0.042s
OK
```

Test coverage hiện có:

- Graph tokenizer normalize `re-index` -> `reindex`.
- Natural language question tìm graph seeds.
- Graph expansion trả confidence metadata.
- Graph-known source filter exclude generated artifacts.
- Path matcher exclude `graphify-out/**`.
- Drift result lines Windows console safe.
- Long PDF extract text và split nhiều chunks.
- Long PDF fixture không lặp exact chunks.
- Section metadata và augmented chunk text.
- PDF page number derived from page boundaries.
- Embedding config default OpenAI large 3072.
- Local sentence-transformer fallback.
- OpenAI embedding payload.
- Rerank dedupe keeps highest scoring duplicate.
- Rule rerank promotes section title match.

### 11.2. Compile check

Command:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
```

Kết quả: exit code `0`.

### 11.3. Runtime/API check

Health response mới nhất:

```json
{
  "ok": true,
  "model": "openai:text-embedding-3-large:3072",
  "embedding_provider": "openai",
  "embedding_dimensions": 3072,
  "graph_nodes": 41
}
```

DB metadata smoke:

```text
(15, 15, 0, 11, 15, 3072, 3072)
```

Ý nghĩa tuple:

```text
total chunks = 15
distinct chunk hashes = 15
duplicate rows = 0
chunks with section_title = 11
chunks with page_number = 15
min vector dims = 3072
max vector dims = 3072
```

## 12. Mapping yêu cầu -> đã trả lời chưa

| Yêu cầu | Trạng thái | Bằng chứng |
|---|---:|---|
 Nghiên cứu Graphify | Done | Section 2.2, refs GitHub/README, graph artifacts |
 Nghiên cứu CocoIndex | Done | Section 2.1, refs GitHub/README/docs, `src/indexing/flow.py` |
 RAG reindex khi đổi embedding model | Done ở POC | `embedding_config.py`, `flow.py`, OpenAI 3072 reindex evidence |
 Dùng Graphify xây graph tăng accuracy/evidence | Done | `graph.json`, `GraphIndex`, graph recall 1.0 |
 Step 1 kiến trúc/framework/strategy | Done | Sections 2, 3, 4 |
 Strategy index data vào database | Done | Section 3, 4, 5 |
 Debate scale nhiều CCU | Done | Section 9 |
 Step 2 demo nhiều loại tài liệu | Done | Section 6, tests, DB evidence |
 Step 3 tối ưu retrieval | Done | Section 7, `api/rerank.py`, report JSON |
 Giả lập tải hỏi đáp | Done historical/local | Section 9, `scripts/load_test.py` |
 Flow end-to-end | Done | Section 4 |
 Chunking/reranking chi tiết | Done | Sections 4.2, 4.4, 7 |
 Bằng chứng cụ thể | Done | Sections 7, 8, 11 |

## 13. Những phần chưa làm và lý do

1. Chưa implement LLM answer generator:
   - Hiện API trả `HybridResponse` cho LLM dùng.
   - Bước tiếp theo là context builder + prompt + answer with citations.

2. Chưa implement cross-encoder reranker thật:
   - Đã có rule reranker deterministic và boundary `src/api/rerank.py`.
   - Cross-encoder sẽ kéo thêm dependency/model runtime.
   - Production nên thêm sau khi có golden dataset lớn để đo tradeoff latency/accuracy.

3. Chưa có distributed cache:
   - In-memory cache đủ POC.
   - Production cần Redis hoặc cache layer tương đương.

4. Chưa có graph DB production:
   - `graph.json` đủ POC.
   - Corpus lớn nên cân nhắc Neo4j/Kuzu hoặc graph snapshot indexed per release.

5. Load test OpenAI high CCU chưa chạy lại:
   - Tránh tiêu tốn API quota lớn.
   - Cần test riêng có quota/rate-limit kế hoạch rõ ràng.

## 14. Bài học kỹ thuật

1. Reindexability không chỉ là chạy lại embedding. Cần thiết kế schema theo dimension của model.
2. Đổi từ 384d sang 3072d là migration schema, không phải chỉ đổi env var.
3. Vector retrieval cần metadata tốt: section, page, hash, spans.
4. Chunk heading quan trọng. Không prepend section thì embedding dễ đánh mất intent theo mục.
5. Top-k raw vector dễ bị duplicate chiếm chỗ. Dedupe nên là bước bắt buộc.
6. Rerank cần tồn tại sau vector search, dù ban đầu chỉ là rule baseline.
7. Graph evidence có giá trị khi trả về relation/confidence/source, không chỉ trả node label.
8. Generated artifacts phải bị exclude khỏi source corpus.
9. Hai pipeline độc lập tạo drift; drift phải đo được.
10. Eval nhỏ chứng minh directionally useful, chưa chứng minh production accuracy.
11. Load test local không đại diện production khi external embedding API tham gia.
12. Production RAG cần observability cho evidence quality, không chỉ latency.

## 15. Kết luận

POC hiện đã trả lời đầy đủ các yêu cầu được giao ở mức kỹ thuật/demo:

- Có nghiên cứu framework CocoIndex và Graphify.
- Có strategy kiến trúc và debate.
- Có pipeline index/reindex bằng CocoIndex.
- Có graph evidence bằng Graphify.
- Có retrieval API kết hợp vector + graph.
- Có metadata/dedupe/rerank để nâng chất lượng retrieval.
- Có demo nhiều loại tài liệu.
- Có eval, long PDF check, tests, compile check, và load-test script.
- Có diagram kiến trúc trong Figma/FigJam.

Kiến trúc hiện tại là lựa chọn hợp lý cho POC và có đường nâng cấp production. Nếu tiếp tục, thứ tự ưu tiên nên là:

1. Thêm LLM answer generator với citations.
2. Thêm cross-encoder reranker sau khi có golden eval lớn hơn.
3. Thêm Redis cache và benchmark OpenAI high CCU.
4. Thêm vector index tuning HNSW/IVFFlat.
5. Thêm graph drift monitoring.
6. Chuẩn hóa doc_id chung giữa vector index và graph index.

## 16. Tài liệu tham khảo và bằng chứng

External references:

- Graphify GitHub: https://github.com/safishamsi/graphify
- Graphify README raw: https://raw.githubusercontent.com/safishamsi/graphify/main/README.md
- CocoIndex GitHub: https://github.com/cocoindex-io/cocoindex
- CocoIndex README raw: https://raw.githubusercontent.com/cocoindex-io/cocoindex/main/README.md
- CocoIndex docs: https://cocoindex.io/docs/

Local implementation:

- `src/indexing/flow.py`
- `src/api/retrieval.py`
- `src/api/rerank.py`
- `src/api/graph_retrieval.py`
- `src/embedding_config.py`
- `scripts/evaluate_retrieval.py`
- `scripts/load_test.py`
- `scripts/drift_test.py`
- `scripts/make_long_pdf.py`

Local evidence:

- `reports/long_pdf_retrieval_check.json`
- `reports/retrieval_eval_optimized.json`
- `docs/retrieval-quality-upgrades.md`
- `docs/openai-embedding-3-large.md`
- `data/docs/graphify-out/graph.json`
- `data/docs/graphify-out/GRAPH_REPORT.md`
- `tests/test_rerank.py`
- `tests/test_long_pdf_ingestion.py`
- `tests/test_graph_retrieval.py`
- `tests/test_embedding_config.py`
- `tests/test_operations.py`

Figma:

- RAG architecture diagrams: https://www.figma.com/board/lKAHjlnRCKCt39Wp3NjDM4
