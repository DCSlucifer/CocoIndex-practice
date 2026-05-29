# RAG Demo Commands

File này gom các lệnh PowerShell riêng lẻ để demo hệ thống RAG hiện tại.

Mục tiêu demo:

1. Verify code và tests.
2. Reindex vector database bằng CocoIndex.
3. Build knowledge graph bằng Graphify.
4. Chạy API retrieval.
5. Query end-to-end.
6. Đọc JSON output của evaluation và long PDF check.
7. Giả lập load hỏi đáp.
8. Demo đổi embedding model bằng `.env` + CocoIndex lifecycle.

## Bảng mục đích từng lệnh chính

| Lệnh | Mục đích | Chứng minh điều gì |
| --- | --- | --- |
| `cd "D:\Rag vsf"` | Đưa terminal về đúng project root. | Tất cả path tương đối như `src`, `data/docs`, `reports` sẽ chạy đúng. |
| `$env:PYTHONPATH="src"` | Cho Python biết module root là thư mục `src`. | Tránh lỗi `No module named indexing` hoặc `No module named api`. |
| `.\.venv\Scripts\python.exe --version` | Kiểm tra Python trong virtual environment. | Terminal đang dùng đúng Python của project. |
| `.\.venv\Scripts\python.exe -c "import indexing.flow; print('import indexing.flow OK')"` | Kiểm tra import pipeline CocoIndex. | Module `src/indexing/flow.py` có thể được Python load. |
| `.\.venv\Scripts\python.exe -m unittest discover -s tests` | Chạy toàn bộ unit tests. | Chunking, metadata, embedding config, graph retrieval, rerank/dedupe đang pass. |
| `.\.venv\Scripts\python.exe -m compileall -q src scripts tests` | Compile toàn bộ source Python. | Code không có lỗi syntax/import compile cơ bản. |
| `$LASTEXITCODE` | Xem exit code của lệnh vừa chạy. | `0` nghĩa là lệnh trước đó thành công. |
| `Get-Content .env ... <redacted>` | Xem cấu hình `.env` nhưng che API key. | Demo được model/provider/dimensions mà không lộ secret. |
| `.\.venv\Scripts\python.exe -m indexing.flow drop` | Xóa target/state index hiện tại của CocoIndex app. | Chuẩn bị rebuild sạch khi đổi embedding model hoặc schema. |
| `.\.venv\Scripts\python.exe -m indexing.flow update` | Chạy CocoIndex indexing pipeline. | Tạo lại vector index trong PostgreSQL pgvector từ `data/docs`. |
| `.\.venv\Scripts\python.exe -m indexing.flow live` | Chạy CocoIndex watch/live mode. | Có thể pickup thay đổi file trong corpus theo mode live. |
| `.\.venv\Scripts\graphify.exe update data/docs` | Chạy Graphify trên corpus. | Sinh knowledge graph từ docs/code/PDF. |
| `Get-ChildItem data\docs\graphify-out` | Xem artifact Graphify. | Có `graph.json`, `GRAPH_REPORT.md`, `graph.html`. |
| `.\.venv\Scripts\python.exe -m uvicorn api.retrieval:app --host 127.0.0.1 --port 8003` | Start FastAPI retrieval service. | API online để query vector + graph evidence. |
| `Invoke-RestMethod http://127.0.0.1:8003/health` | Kiểm tra API health. | API đang dùng đúng embedding model/dimensions và đã load graph. |
| `$body = @{ ... } \| ConvertTo-Json` | Tạo JSON body cho query. | Request có `question`, `top_k`, `graph_depth`. |
| `Invoke-RestMethod -Method Post -Uri ".../query" ...` | Gửi câu hỏi vào RAG API. | Chạy flow online end-to-end. |
| `$r.timing_ms` | Xem latency breakdown. | Biết thời gian embed, vector search, graph, rerank. |
| `$r.vector_hits \| Select-Object ...` | Xem kết quả vector retrieval. | Có source, section, page, score, rerank score, chunk hash. |
| `$r.graph_hits \| Select-Object ...` | Xem kết quả graph retrieval. | Có graph evidence và confidence tag từ Graphify. |
| `$r.vector_hits[0].text` | Xem nội dung chunk top 1. | Kiểm tra evidence có đúng nội dung cần trả lời không. |
| `.\.venv\Scripts\python.exe scripts\evaluate_retrieval.py --url ... --out reports\retrieval_eval_optimized.json` | Chạy bộ evaluation retrieval. | Đo vector recall, graph recall, confidence recall, latency. |
| `$eval = Get-Content reports\retrieval_eval_optimized.json -Raw \| ConvertFrom-Json` | Load JSON eval vào PowerShell object. | Có thể đọc summary/results dễ hơn. |
| `$eval.summary` | Xem kết quả tổng hợp evaluation. | Biết recall và latency tổng quan. |
| `$eval.results \| Select-Object ...` | Xem kết quả từng test case. | Biết case nào vector/graph/confidence pass. |
| `$long = Get-Content reports\long_pdf_retrieval_check.json -Raw \| ConvertFrom-Json` | Load JSON long PDF check. | Đọc evidence về chunking, dedupe, section/page metadata. |
| `$long.db_evidence` | Xem thống kê DB/index. | Tổng chunks, docs, duplicate rows, model, dimensions. |
| `$long.checks \| Select-Object ...` | Xem kết quả từng long PDF query. | Biết evidence đúng đứng rank mấy và score bao nhiêu. |
| `$long.checks[0].top_sections` | Xem section được retrieve. | Chứng minh section-aware chunking hoạt động. |
| `$long.checks[0].top_pages` | Xem page được retrieve. | Chứng minh PDF page metadata hoạt động. |
| `$long.checks[0].evidence_snippet` | Xem đoạn evidence đúng. | Chứng minh câu hỏi lấy đúng nội dung trong long PDF. |
| `.\.venv\Scripts\python.exe scripts\load_test.py --url ... --levels 1,10,50 --reqs 10` | Chạy load test nhỏ. | Demo API xử lý concurrent QA ở mức vừa. |
| `.\.venv\Scripts\python.exe scripts\load_test.py --url ... --levels 1,10,50,100 --reqs 20` | Chạy load test lớn hơn. | Có dữ liệu p50/p95/p99/qps để debate scale. |
| `.\.venv\Scripts\python.exe scripts\load_test.py --url ... --cold` | Chạy load test không warmup. | So sánh cold path với warm path/cache path. |
| `.\.venv\Scripts\python.exe scripts\drift_test.py` | Tạo file mới và trigger CocoIndex + Graphify song song. | Đo drift window giữa vector index và graph index. |
| Sửa `.env` sang `text-embedding-3-small`, `1536` | Đổi embedding model/dimensions. | Chứng minh model migration bắt đầu từ config, không sửa code pipeline. |
| `drop` rồi `update` sau khi sửa `.env` | Rebuild vector DB theo model mới. | CocoIndex rebuild index theo config embedding mới. |
| Restart `uvicorn` sau khi sửa `.env` | Cho API đọc lại config mới. | `/health` sẽ đổi sang model/dimensions mới. |

## 0. Chuẩn bị terminal

Chạy trong PowerShell tại project root:

```powershell
cd "D:\Rag vsf"
```

Set `PYTHONPATH` cho terminal hiện tại:

```powershell
$env:PYTHONPATH="src"
```

Kiểm tra Python trong virtual environment:

```powershell
.\.venv\Scripts\python.exe --version
```

Kiểm tra import module indexing:

```powershell
.\.venv\Scripts\python.exe -c "import indexing.flow; print('import indexing.flow OK')"
```

Nếu thiếu dòng `$env:PYTHONPATH="src"`, lệnh `python -m indexing.flow` sẽ lỗi:

```text
ModuleNotFoundError: No module named 'indexing'
```

## 1. Verify code trước khi demo

Chạy unit tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Kết quả kỳ vọng:

```text
Ran 16 tests
OK
```

Chạy compile check:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
```

Nếu lệnh không in gì và quay lại prompt, nghĩa là compile pass.

Kiểm tra exit code:

```powershell
$LASTEXITCODE
```

Kết quả kỳ vọng:

```text
0
```

Lưu ý: không paste lặp 2 lần cùng một lệnh compileall trên một dòng. Nếu dán dính 2 lệnh, `compileall` sẽ báo `unrecognized arguments`.

## 2. Kiểm tra cấu hình embedding trong `.env`

Không show API key khi demo.

Xem các biến không nhạy cảm:

```powershell
Get-Content .env | ForEach-Object { if ($_ -match '^OPENAI_API_KEY=') { 'OPENAI_API_KEY=<redacted>' } else { $_ } }
```

Cấu hình hiện tại nên có dạng:

```env
POSTGRES_URL=postgresql://postgres:ragpass@localhost:5433/ragdb
PG_CONN=postgresql://postgres:ragpass@localhost:5433/ragdb
COCOINDEX_DB=.cocoindex
EMBED_PROVIDER=openai
EMBED_MODEL=text-embedding-3-large
EMBED_DIMENSIONS=3072
OPENAI_API_KEY=<redacted>
```

Ý nghĩa:

- `EMBED_PROVIDER`: chọn provider embedding.
- `EMBED_MODEL`: chọn model embedding.
- `EMBED_DIMENSIONS`: dimension của vector.
- `POSTGRES_URL` hoặc `PG_CONN`: database chứa pgvector.
- `COCOINDEX_DB`: state/cache local của CocoIndex.

## 3. Demo CocoIndex reindex vector database

Lệnh `drop` sẽ xóa target index/state hiện tại của app CocoIndex. Chỉ chạy khi muốn rebuild lại index.

Drop index hiện tại:

```powershell
.\.venv\Scripts\python.exe -m indexing.flow drop
```

Build lại index:

```powershell
.\.venv\Scripts\python.exe -m indexing.flow update
```

Ý nghĩa khi trình bày:

```text
CocoIndex đọc data/docs
-> extract text từ md, txt, py, pdf
-> split chunk 800 overlap 120
-> thêm chunk_hash, section_title, page_number
-> gọi OpenAI text-embedding-3-large
-> ghi vector vào PostgreSQL pgvector table rag.doc_chunks
```

Chạy incremental update không drop:

```powershell
.\.venv\Scripts\python.exe -m indexing.flow update
```

Chạy live mode để watch thay đổi file:

```powershell
.\.venv\Scripts\python.exe -m indexing.flow live
```

## 4. Demo Graphify build knowledge graph

Chạy Graphify update:

```powershell
.\.venv\Scripts\graphify.exe update data/docs
```

Kiểm tra artifact được sinh ra:

```powershell
Get-ChildItem data\docs\graphify-out
```

Các file quan trọng:

```text
data/docs/graphify-out/graph.json
data/docs/graphify-out/GRAPH_REPORT.md
data/docs/graphify-out/graph.html
```

Ý nghĩa khi trình bày:

```text
Graphify không tạo vector index.
Graphify tạo knowledge graph từ cùng corpus.
Output graph.json được API retrieval đọc để bổ sung graph evidence.
Graph evidence có node, edge, source, confidence như EXTRACTED, INFERRED, AMBIGUOUS.
```

## 5. Start API retrieval

Mở terminal mới.

Vào project root:

```powershell
cd "D:\Rag vsf"
```

Set module path:

```powershell
$env:PYTHONPATH="src"
```

Start FastAPI bằng Uvicorn:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.retrieval:app --host 127.0.0.1 --port 8003
```

Giữ terminal này chạy.

## 6. Check API health

Mở terminal khác.

Vào project root:

```powershell
cd "D:\Rag vsf"
```

Gọi health endpoint:

```powershell
Invoke-RestMethod http://127.0.0.1:8003/health
```

Kết quả kỳ vọng:

```text
ok                    True
model                 openai:text-embedding-3-large:3072
embedding_provider    openai
embedding_dimensions  3072
graph_nodes           41
```

Cách đọc:

- `model`: embedding model đang được API dùng.
- `embedding_dimensions`: dimension query embedding.
- `graph_nodes`: số node API đọc được từ Graphify graph.
- Nếu đổi `.env` nhưng health vẫn hiện model cũ, cần restart API.

## 7. Demo query end-to-end

Tạo request body:

```powershell
$body = @{
  question = "How does the system reindex when embedding model changes?"
  top_k = 5
  graph_depth = 1
} | ConvertTo-Json
```

Gọi API:

```powershell
$r = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8003/query" -ContentType "application/json" -Body $body
```

Xem thông tin tổng quan:

```powershell
$r | Select-Object question, model, cached
```

Xem timing:

```powershell
$r.timing_ms
```

Xem vector hits:

```powershell
$r.vector_hits | Select-Object score, rerank_score, source_path, section_title, page_number, chunk_hash
```

Xem graph hits:

```powershell
$r.graph_hits | Select-Object confidence, source_path
```

Xem snippet đầu tiên:

```powershell
$r.vector_hits[0].text
```

Cách đọc response:

- `vector_hits`: evidence lấy từ pgvector.
- `score`: vector similarity gốc.
- `rerank_score`: score sau rule rerank.
- `source_path`: file nguồn.
- `section_title`: heading được prepend vào chunk.
- `page_number`: page PDF nếu có.
- `chunk_hash`: hash dùng để dedupe.
- `graph_hits`: evidence lấy từ Graphify graph.
- `confidence`: độ tin cậy của graph edge, ví dụ `EXTRACTED`.

## 8. Demo query Graphify confidence tags

Tạo request body:

```powershell
$body = @{
  question = "What confidence tags does graphify use on edges?"
  top_k = 5
  graph_depth = 1
} | ConvertTo-Json
```

Gọi API:

```powershell
$r = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8003/query" -ContentType "application/json" -Body $body
```

Xem graph evidence:

```powershell
$r.graph_hits | Select-Object confidence, source_path
```

Điểm cần nói:

```text
Vector search tìm tài liệu liên quan.
Graphify bổ sung evidence có cấu trúc và confidence tag.
Điều này giúp LLM biết evidence nào là extract trực tiếp, evidence nào là suy luận.
```

## 9. Chạy retrieval evaluation

Chạy evaluation và ghi JSON:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_retrieval.py --url http://127.0.0.1:8003/query --out reports\retrieval_eval_optimized.json
```

Đọc summary:

```powershell
$eval = Get-Content reports\retrieval_eval_optimized.json -Raw | ConvertFrom-Json
```

```powershell
$eval.summary
```

Đọc từng case:

```powershell
$eval.results | Select-Object id, vector_ok, graph_ok, confidence_ok, vector_only_score, hybrid_score, latency_ms
```

Cách đọc `reports/retrieval_eval_optimized.json`:

- `summary.cases`: số test case.
- `summary.vector_source_recall`: tỷ lệ query tìm đúng source bằng vector search.
- `summary.graph_evidence_recall`: tỷ lệ query tìm đúng graph evidence.
- `summary.confidence_tag_recall`: tỷ lệ graph hit có confidence tag hợp lệ.
- `summary.avg_vector_only_score`: điểm trung bình nếu chỉ tính vector.
- `summary.avg_hybrid_score`: điểm trung bình khi tính vector + graph + confidence.
- `summary.p50_latency_ms`: median latency.
- `summary.max_latency_ms`: latency chậm nhất trong eval.

Kết quả tốt hiện tại:

```text
vector_source_recall = 1.0
graph_evidence_recall = 1.0
confidence_tag_recall = 1.0
avg_vector_only_score = 1
avg_hybrid_score = 3
```

Ý nghĩa:

```text
Vector-only tìm đúng source.
Hybrid tốt hơn vì ngoài source còn tìm đúng graph evidence và confidence tag.
```

## 10. Đọc long PDF retrieval check

Đọc file JSON:

```powershell
$long = Get-Content reports\long_pdf_retrieval_check.json -Raw | ConvertFrom-Json
```

Xem evidence từ DB:

```powershell
$long.db_evidence
```

Xem các check:

```powershell
$long.checks | Select-Object question, evidence_marker, evidence_rank, best_vector_score, best_rerank_score
```

Xem top sources của check đầu tiên:

```powershell
$long.checks[0].top_sources
```

Xem top sections:

```powershell
$long.checks[0].top_sections
```

Xem top pages:

```powershell
$long.checks[0].top_pages
```

Xem evidence snippet:

```powershell
$long.checks[0].evidence_snippet
```

Cách đọc `reports/long_pdf_retrieval_check.json`:

- `db_evidence.total_chunks`: tổng chunk đã index.
- `db_evidence.total_docs`: tổng file source đã index.
- `db_evidence.long_pdf_chunks`: số chunk đến từ long PDF.
- `db_evidence.distinct_chunk_hashes`: số hash khác nhau.
- `db_evidence.duplicate_chunk_rows`: số duplicate row. Kỳ vọng là `0`.
- `db_evidence.chunks_with_section_title`: số chunk có section title.
- `db_evidence.chunks_with_page_number`: số chunk có page number.
- `db_evidence.file_types`: loại tài liệu đã index, ví dụ `.md`, `.pdf`, `.py`.
- `db_evidence.embedding_model`: model embedding đã dùng để index.
- `db_evidence.embedding_dimensions`: dimension vector.
- `checks[].evidence_rank`: rank của evidence đúng trong top-k. Rank `1` là tốt nhất.
- `checks[].best_vector_score`: score vector gốc cao nhất.
- `checks[].best_rerank_score`: score sau rerank cao nhất.
- `checks[].top_sections`: section retrieved.
- `checks[].top_pages`: page retrieved.
- `checks[].evidence_snippet`: đoạn evidence đúng.

Điểm đẹp để trình bày:

```text
duplicate_chunk_rows = 0
embedding_model = openai:text-embedding-3-large:3072
evidence_rank = 1
best_rerank_score > best_vector_score
```

Ý nghĩa:

```text
Dedupe hoạt động.
Embedding model mới đã được dùng.
Evidence đúng lên top 1.
Reranker làm tăng điểm cho section/evidence phù hợp.
```

## 11. Demo load test hỏi đáp

Chạy load nhỏ:

```powershell
.\.venv\Scripts\python.exe scripts\load_test.py --url http://127.0.0.1:8003/query --levels 1,10,50 --reqs 10
```

Chạy load lớn hơn:

```powershell
.\.venv\Scripts\python.exe scripts\load_test.py --url http://127.0.0.1:8003/query --levels 1,10,50,100 --reqs 20
```

Chạy cold load không warmup:

```powershell
.\.venv\Scripts\python.exe scripts\load_test.py --url http://127.0.0.1:8003/query --levels 1,10,50 --reqs 10 --cold
```

Cách đọc output:

- `CCU`: số user đồng thời giả lập.
- `reqs`: tổng request.
- `ok`: request thành công.
- `err`: request lỗi.
- `p50`: median latency.
- `p95`: 95% request nhanh hơn mốc này.
- `p99`: 99% request nhanh hơn mốc này.
- `avg`: latency trung bình.
- `qps`: request per second.

Điểm cần nói:

```text
Load test local chứng minh API xử lý concurrent query.
Production muốn scale nhiều CCU cần nhiều API replicas, DB pool tuning, pgvector index tuning, cache phân tán, và shadow index khi đổi embedding model.
```

## 12. Demo drift giữa CocoIndex và Graphify

Chạy drift test:

```powershell
.\.venv\Scripts\python.exe scripts\drift_test.py
```

Cách đọc output:

- `Cocoindex incremental`: thời gian CocoIndex pickup file mới và update vector index.
- `Graphify incremental`: thời gian Graphify pickup file mới và update graph.
- `Drift window`: chênh lệch thời gian giữa 2 pipeline.

Ý nghĩa:

```text
Vì hệ thống có 2 pipeline song song, vector index và graph index có thể lệch nhau trong một khoảng ngắn.
Production cần monitor drift hoặc orchestrate job để đồng bộ.
```

## 13. Demo đổi embedding model và reindex

Mục tiêu:

```text
Chứng minh khi đổi embedding model thì không sửa code pipeline.
Chỉ sửa .env rồi chạy lại CocoIndex lifecycle.
```

Đổi `.env` sang small:

```env
EMBED_PROVIDER=openai
EMBED_MODEL=text-embedding-3-small
EMBED_DIMENSIONS=1536
```

Reindex:

```powershell
.\.venv\Scripts\python.exe -m indexing.flow drop
```

```powershell
.\.venv\Scripts\python.exe -m indexing.flow update
```

Restart API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.retrieval:app --host 127.0.0.1 --port 8003
```

Check health:

```powershell
Invoke-RestMethod http://127.0.0.1:8003/health
```

Kỳ vọng:

```text
model                 openai:text-embedding-3-small:1536
embedding_dimensions  1536
```

Đổi lại large sau demo:

```env
EMBED_PROVIDER=openai
EMBED_MODEL=text-embedding-3-large
EMBED_DIMENSIONS=3072
```

Reindex lại large:

```powershell
.\.venv\Scripts\python.exe -m indexing.flow drop
```

```powershell
.\.venv\Scripts\python.exe -m indexing.flow update
```

Restart API rồi check health:

```powershell
Invoke-RestMethod http://127.0.0.1:8003/health
```

Kỳ vọng:

```text
model                 openai:text-embedding-3-large:3072
embedding_dimensions  3072
```

Điểm cần nói:

```text
Nếu không có CocoIndex, đổi model thường phải tự viết lại scan file, extract, split, embed, upsert, migrate schema.
Ở POC này, code pipeline giữ nguyên.
Ta chỉ đổi .env và chạy CocoIndex drop/update.
```

## 14. Troubleshooting nhanh

### Lỗi `No module named indexing`

Chạy:

```powershell
$env:PYTHONPATH="src"
```

Sau đó chạy lại:

```powershell
.\.venv\Scripts\python.exe -m indexing.flow update
```

### Lỗi API vẫn dùng model cũ

Restart Uvicorn process.

API đọc `.env` lúc process start, nên sửa `.env` xong phải restart.

### Lỗi vector dimension mismatch

Nguyên nhân thường là DB đang có vector dimension cũ nhưng API/query dùng model mới.

Fix trong POC:

```powershell
.\.venv\Scripts\python.exe -m indexing.flow drop
```

```powershell
.\.venv\Scripts\python.exe -m indexing.flow update
```

Sau đó restart API.

### Lỗi Postgres connection

Kiểm tra `.env`:

```powershell
Get-Content .env | Select-String "POSTGRES_URL","PG_CONN"
```

Kiểm tra service Postgres đang chạy ở port `5433`.

### Lỗi OpenAI key

Kiểm tra biến tồn tại, không in key thật khi demo:

```powershell
Get-Content .env | ForEach-Object { if ($_ -match '^OPENAI_API_KEY=') { 'OPENAI_API_KEY=<redacted>' } }
```

### Lỗi port 8003 đang bận

Chạy API ở port khác:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.retrieval:app --host 127.0.0.1 --port 8004
```

Sau đó đổi URL trong các lệnh query/eval/load sang:

```text
http://127.0.0.1:8004/query
```

## 15. Checklist trình bày demo

1. Chạy tests và compile check.
2. Chạy CocoIndex drop/update.
3. Chạy Graphify update.
4. Start API.
5. Check `/health`.
6. Query reindex question.
7. Show `vector_hits`.
8. Show `graph_hits`.
9. Chạy `evaluate_retrieval.py`.
10. Đọc `retrieval_eval_optimized.json`.
11. Đọc `long_pdf_retrieval_check.json`.
12. Chạy `load_test.py`.
13. Giải thích đổi `.env` + CocoIndex lifecycle để reindex khi đổi embedding model.
