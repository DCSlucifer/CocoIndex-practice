# Reindexable Hybrid RAG với CocoIndex, Graphify và pgvector

Đây là POC RAG có khả năng reindex khi thay đổi embedding model, kết hợp hai nguồn evidence:

- **Vector evidence** từ PostgreSQL/pgvector, được build bằng CocoIndex.
- **Graph evidence** từ Graphify, được lưu trong `graph.json` và dùng để mở rộng ngữ cảnh truy vấn.

Hệ thống hiện hỗ trợ ingest nhiều loại tài liệu (`.md`, `.txt`, `.py`, `.pdf`), truy vấn qua FastAPI, sinh câu trả lời có citation, chạy evaluation, kiểm tra long PDF, đo drift giữa hai pipeline và load test cục bộ.

> 📘 Muốn hiểu sâu thuật toán/hàm core, kiến trúc, cách demo và học CocoIndex/Graphify: xem [`docs/core-guide.md`](docs/core-guide.md).

## Trạng thái hiện tại

| Hạng mục | Trạng thái | Bằng chứng chính |
| --- | --- | --- |
| Nghiên cứu CocoIndex | Hoàn thành | `docs/research/cocoindex.md`, `docs/reports/2026-05-28-rag-graphify-cocoindex-final-report.md` |
| Nghiên cứu Graphify | Hoàn thành | `data/docs/graphify-out/graph.json`, `data/docs/graphify-out/GRAPH_REPORT.md` |
| Kiến trúc RAG có thể reindex | Hoàn thành ở mức POC | `src/indexing/flow.py`, `src/embedding_config.py` |
| Graph evidence để tăng độ tin cậy retrieval | Hoàn thành | `src/api/graph_retrieval.py`, `reports/retrieval_eval_optimized.json` |
| Demo nhiều loại tài liệu | Hoàn thành | `data/docs`, `tests/test_long_pdf_ingestion.py` |
| Tối ưu retrieval | Hoàn thành | `src/api/rerank.py`, `docs/retrieval-quality-upgrades.md` |
| API hỏi đáp và UI demo | Hoàn thành | `src/api/retrieval.py`, `src/api/static/demo.html` |
| Load test, drift test, evaluation | Hoàn thành ở mức local POC | `scripts/load_test.py`, `scripts/drift_test.py`, `scripts/evaluate_retrieval.py` |

Kết quả evaluation gần nhất trong `reports/retrieval_eval_optimized.json`:

- `vector_source_recall = 1.0`
- `graph_evidence_recall = 1.0`
- `confidence_tag_recall = 1.0`
- `avg_vector_only_score = 1`
- `avg_hybrid_score = 3`

Kết quả long PDF check gần nhất trong `reports/long_pdf_retrieval_check.json`:

- `total_chunks = 15`
- `duplicate_chunk_rows = 0`
- `chunks_with_section_title = 11`
- `chunks_with_page_number = 15`
- `embedding_model = openai:text-embedding-3-large:3072`
- hai case long PDF chính đều đưa evidence đúng lên `rank 1`

## Kiến trúc

Diagram kiến trúc được vẽ theo C4 model bằng `plantuml-stdlib/C4-PlantUML`, dựa trên cấu trúc source hiện tại trong `src/`, `scripts/`, `.env.example`, corpus và runtime artifacts.
Không dùng ảnh kiến trúc cũ làm nguồn suy luận.

### C4 Level 2 - Container

![Reindexable Hybrid RAG C4 Container Diagram](docs/architecture-c4-container.png)

Nguồn PlantUML: [`docs/architecture-c4-container.puml`](docs/architecture-c4-container.puml)
và bản SVG: [`docs/architecture-c4-container.svg`](docs/architecture-c4-container.svg).

### C4 Level 3 - Component: FastAPI Retrieval API

![FastAPI Retrieval API C4 Component Diagram](docs/architecture-c4-component-api.png)

Nguồn PlantUML: [`docs/architecture-c4-component-api.puml`](docs/architecture-c4-component-api.puml)
và bản SVG: [`docs/architecture-c4-component-api.svg`](docs/architecture-c4-component-api.svg).

> README tập trung Level 2 (Container) và Level 3 (Component); bỏ Level 1 (Context) và Level 4 (Code).
> Đường nối dùng `skinparam linetype ortho` để vuông góc, không cong/ngoằn ngoèo.

#### Render lại

Cần `plantuml.jar` + Java (Graphviz `dot` đã được PlantUML đóng gói sẵn):

```powershell
# render PNG rồi SVG cho cả 3 .puml
java -jar plantuml.jar -tpng docs/architecture-c4-*.puml
java -jar plantuml.jar -tsvg docs/architecture-c4-*.puml
```

Lưu ý: PlantUML đặt tên output theo tên sau `@startuml` (vd `Reindexable_Hybrid_RAG_C4_Container.png`),
không theo tên file `.puml`, nên cần đổi tên lại về `architecture-c4-*.{png,svg}` cho khớp các link ở trên.

Thiết kế chọn **Strategy B: hai pipeline song song**:

1. **CocoIndex pipeline** đọc corpus, extract text, chunk, embed và ghi vector vào `rag.doc_chunks`.
2. **Graphify pipeline** đọc cùng corpus, sinh graph artifacts trong `data/docs/graphify-out`.
3. **FastAPI retrieval service** kết hợp pgvector top-k, dedupe, rule rerank và graph expansion.
4. **Answer API** dùng vector citations và graph context để gọi LLM trả lời có nguồn.

Lý do chọn cách này:

- Đổi embedding model chủ yếu ảnh hưởng vector index, không bắt buộc rebuild graph.
- Graphify giữ đúng vai trò graph extraction, không bị biến thành tài liệu phụ để index nhầm.
- CocoIndex giữ đúng vai trò incremental target sync và reindex lifecycle.
- Nhược điểm là có drift giữa vector index và graph index; POC đã có `scripts/drift_test.py` để đo.

## Các phần đã implement

### Indexing bằng CocoIndex

File chính: `src/indexing/flow.py`

Pipeline:

```text
data/docs
  -> localfs.walk_dir
  -> exclude graphify-out/**
  -> extract text từ md/txt/py/pdf
  -> split chunk size 800, overlap 120
  -> derive section_title, page_number, chunk_hash
  -> prepend Section: <title> vào chunk text
  -> embed bằng provider trong .env
  -> write vào PostgreSQL pgvector table rag.doc_chunks
```

Metadata được lưu cùng chunk:

- `source_path`
- `file_type`
- `chunk_start`
- `chunk_end`
- `text`
- `chunk_hash`
- `section_title`
- `page_number`
- `model_name`
- `embedding`

### Embedding configuration

File chính: `src/embedding_config.py`

Mặc định POC đang dùng:

```env
EMBED_PROVIDER=openai
EMBED_MODEL=text-embedding-3-large
EMBED_DIMENSIONS=3072
```

Fallback local cho test/offline:

```env
EMBED_PROVIDER=sentence_transformers
EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBED_DIMENSIONS=384
```

Lưu ý: đổi từ model 384 dimensions sang 3072 dimensions là migration schema vector, không chỉ là đổi env var. Với POC nhỏ, cách an toàn là `drop` rồi `update`. Production nên dùng shadow table hoặc shadow column.

### Graph evidence bằng Graphify

Artifacts:

```text
data/docs/graphify-out/graph.json
data/docs/graphify-out/GRAPH_REPORT.md
data/docs/graphify-out/graph.html
```

File runtime chính: `src/api/graph_retrieval.py`

GraphIndex hiện làm các việc:

- load `graph.json`
- normalize token như `re-index` thành `reindex`
- rank node theo query và vector context
- expand neighbor theo `graph_depth`
- trả về `node`, `relation`, `confidence`, `source_file`, `source_location`, `seed`

### Retrieval API

File chính: `src/api/retrieval.py`

Endpoints:

| Endpoint | Mục đích |
| --- | --- |
| `GET /health` | Kiểm tra model, dimension, graph nodes, cache, pool |
| `POST /query` | Trả vector hits + graph hits |
| `POST /answer` | Sinh final answer có citations |
| `GET /demo` | UI demo trong browser |

Query path:

```text
question
  -> response cache
  -> query embedding cache
  -> OpenAI hoặc sentence-transformers embedding
  -> pgvector search LIMIT top_k * 8
  -> dedupe by chunk_hash
  -> deterministic rule rerank
  -> annotate graph_known (cross-check vs graph corpus, không drop)
  -> graph expansion
  -> HybridResponse
```

### Retrieval quality upgrades

File chính: `src/api/rerank.py`

Đã thêm:

- overfetch `top_k * 8`
- dedupe theo `chunk_hash`, fallback normalized text
- section-aware embedding text
- `section_title` và `page_number` để citation tốt hơn
- rule rerank dựa trên section overlap, token overlap và phrase bonus
- response cache và query embedding cache trong memory (đã bảo vệ thread-safe bằng lock)
- graph cross-validation: mỗi vector hit có thêm cờ `graph_known` cho biết graph có corroborate source doc đó không. Đây là annotation **không phá hủy** — không drop hit nào, nên evidence từ PDF (Graphify không ingest PDF) vẫn được giữ. `HybridResponse.graph_known_doc_filter_applied=true` khi graph có corpus để cross-check.

## Cấu trúc thư mục

```text
.
├── data/docs/                         # corpus demo: markdown, PDF, Python code
├── data/docs/graphify-out/            # graph artifacts do Graphify sinh ra
├── docs/                              # research, report, command notes, diagram
├── reports/                           # JSON evaluation và runtime logs
├── scripts/
│   ├── evaluate_retrieval.py          # curated retrieval evaluation
│   ├── load_test.py                   # local concurrent query load test
│   ├── drift_test.py                  # đo drift CocoIndex vs Graphify
│   ├── reindex_test.py                # e2e reindex test: build từng model, assert DB dim + model_name
│   ├── serve_demo.ps1                 # one-command demo launcher (Postgres + index + graph + API)
│   ├── make_pdf.py                    # tạo PDF fixture ngắn
│   └── make_long_pdf.py               # tạo long PDF fixture
├── src/
│   ├── embedding_config.py            # embedding provider/model config
│   ├── api/
│   │   ├── retrieval.py               # FastAPI app
│   │   ├── graph_retrieval.py         # graph.json query helper
│   │   ├── rerank.py                  # dedupe + rerank
│   │   ├── answering.py               # answer generation + citations
│   │   └── static/demo.html           # browser demo UI
│   └── indexing/flow.py               # CocoIndex indexing app
└── tests/                             # regression tests
```

## Yêu cầu môi trường

Đã verify trên:

- Windows PowerShell
- Python `3.13.7`
- PostgreSQL có extension `vector`
- CocoIndex `1.0.6`
- Graphify package `graphifyy==0.8.22`
- FastAPI `0.136.3`
- Uvicorn `0.48.0`

Database mặc định trong `.env.example`:

```env
POSTGRES_URL=postgresql://postgres:ragpass@localhost:5433/ragdb
PG_CONN=postgresql://postgres:ragpass@localhost:5433/ragdb
```

Nếu cần chạy Postgres bằng Docker:

```powershell
docker run --name rag-pgvector `
  -e POSTGRES_PASSWORD=ragpass `
  -e POSTGRES_DB=ragdb `
  -p 5433:5432 `
  -d pgvector/pgvector:pg16
```

Nếu container đã tồn tại:

```powershell
docker start rag-pgvector
```

## Cài đặt

Vào project root:

```powershell
cd "D:\Rag vsf"
```

Nếu đã có `.venv` trong repo này, có thể dùng luôn. Nếu cần tạo lại:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
```

Cài dependencies (khuyến nghị, version đã pin và verify trong `requirements.txt`):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Hoặc cài thủ công từng package nếu cần:

```powershell
.\.venv\Scripts\python.exe -m pip install `
  cocoindex==1.0.6 `
  graphifyy==0.8.22 `
  fastapi==0.136.3 `
  uvicorn==0.48.0 `
  asyncpg==0.31.0 `
  "psycopg[binary,pool]==3.3.4" `
  pgvector==0.4.2 `
  pypdf==6.12.2 `
  python-dotenv==1.2.2 `
  httpx==0.28.1 `
  numpy==2.4.6 `
  sentence-transformers==5.5.1 `
  reportlab==4.5.1
```

Tạo file cấu hình:

```powershell
Copy-Item .env.example .env
notepad .env
```

Điền `OPENAI_API_KEY` nếu dùng OpenAI embedding hoặc `/answer`. Không commit hoặc share `.env`.

Mỗi terminal chạy lệnh Python cần set module path:

```powershell
$env:PYTHONPATH="src"
```

## Chạy indexing

### 1. Build hoặc rebuild vector index bằng CocoIndex

Chỉ dùng `drop` khi muốn xóa index/state hiện tại để rebuild sạch:

```powershell
.\.venv\Scripts\python.exe -m indexing.flow drop
```

Index corpus vào PostgreSQL/pgvector:

```powershell
.\.venv\Scripts\python.exe -m indexing.flow update
```

Chạy live mode để watch thay đổi file:

```powershell
.\.venv\Scripts\python.exe -m indexing.flow live
```

### 2. Build graph bằng Graphify

```powershell
.\.venv\Scripts\graphify.exe update data/docs
```

Kiểm tra output:

```powershell
Get-ChildItem data\docs\graphify-out
```

Cần thấy tối thiểu:

```text
graph.json
GRAPH_REPORT.md
graph.html
```

## Chạy API và UI

### Cách nhanh nhất: một lệnh

Script `scripts/serve_demo.ps1` gộp toàn bộ bước demo: kiểm tra/khởi động Postgres, build vector index + graph nếu thiếu (incremental, **không** drop), rồi start API.

```powershell
.\scripts\serve_demo.ps1
```

Mở `http://127.0.0.1:8003/demo` sau khi script báo API đã chạy.

Tùy chọn:

```powershell
.\scripts\serve_demo.ps1 -Rebuild        # drop + build lại index/graph từ đầu
.\scripts\serve_demo.ps1 -Port 8004      # chạy port khác
.\scripts\serve_demo.ps1 -SkipBuild      # chỉ start API, không đụng index/graph
```

### Cách thủ công

Start API trên port `8003`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.retrieval:app --host 127.0.0.1 --port 8003
```

Mở UI demo:

```text
http://127.0.0.1:8003/demo
```

UI cho phép bấm câu hỏi mẫu rồi xem answer, citations, vector evidence, graph evidence và timing. Checkbox **Evidence only (no LLM)** chuyển sang gọi `/query` thay vì `/answer`: chỉ lấy vector + graph evidence, không gọi LLM — nhanh hơn, không tốn chi phí answer, hữu ích khi demo retrieval mà không cần sinh câu trả lời.

Mỗi vector card có badge **graph ✓/✗** (theo cờ `graph_known`) cho biết graph có corroborate source doc không. Khi API offline hoặc index lệch dimension so với config, UI hiện banner cảnh báo kèm lệnh khắc phục (start API / reindex).

Health check từ terminal khác:

```powershell
Invoke-RestMethod http://127.0.0.1:8003/health
```

Kỳ vọng các trường quan trọng:

```text
ok                       True
model                    openai:text-embedding-3-large:3072
embedding_provider       openai
embedding_dimensions     3072
db_embedding_dimensions  [3072]
index_ready              True
graph_nodes              > 0
```

`/health` còn so chiều vector trong DB với config: nếu lệch (đổi model mà chưa reindex), `index_ready=false` và `warnings` sẽ chỉ rõ cần `indexing.flow drop + update`, thay vì để `/query` vỡ 500 lúc runtime.

## Gọi API thủ công

### Query evidence layer

```powershell
$body = @{
  question = "How does the system reindex when embedding model changes?"
  top_k = 5
  graph_depth = 1
} | ConvertTo-Json
```

```powershell
$r = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8003/query" `
  -ContentType "application/json" `
  -Body $body
```

Xem timing:

```powershell
$r.timing_ms
```

Xem vector evidence:

```powershell
$r.vector_hits | Select-Object source_path, section_title, page_number, vector_score, rerank_score, graph_known
```

Xem graph evidence:

```powershell
$r.graph_hits | Select-Object confidence, relation, source_file, distance
```

### Generate final answer with citations

```powershell
$a = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8003/answer" `
  -ContentType "application/json" `
  -Body $body
```

Xem câu trả lời:

```powershell
$a.answer
```

Xem citations:

```powershell
$a.citations | Select-Object id, source_name, section_title, page_number
```

Xem model metadata:

```powershell
$a | Select-Object model, retrieval_model, cached
```

## Chạy test

### Unit tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Kết quả kỳ vọng: toàn bộ test pass và kết thúc bằng `OK`.

Các nhóm test chính:

- embedding config và OpenAI embedding payload
- Graphify graph retrieval, token normalization, confidence metadata
- path matcher exclude `graphify-out/**`
- long PDF extraction, section/page metadata, duplicate chunk check
- dedupe và rule rerank
- answer message/citation builder
- demo UI contract

### Compile check

```powershell
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
```

Nếu command không in gì và `$LASTEXITCODE` là `0`, source compile pass.

```powershell
$LASTEXITCODE
```

### Retrieval evaluation

Cần API đang chạy trước.

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_retrieval.py `
  --url http://127.0.0.1:8003/query `
  --out reports\retrieval_eval_optimized.json
```

Đọc summary:

```powershell
$eval = Get-Content reports\retrieval_eval_optimized.json -Raw | ConvertFrom-Json
$eval.summary
```

Đọc từng case:

```powershell
$eval.results | Select-Object id, vector_ok, graph_ok, confidence_ok, latency_ms
```

### Long PDF evidence check

Đọc report đã sinh:

```powershell
$long = Get-Content reports\long_pdf_retrieval_check.json -Raw | ConvertFrom-Json
$long.db_evidence
```

Xem các check chính:

```powershell
$long.checks | Select-Object question, evidence_marker, evidence_rank, best_vector_score, best_rerank_score
```

### Load test local

Cần API đang chạy trước.

Load nhỏ:

```powershell
.\.venv\Scripts\python.exe scripts\load_test.py `
  --url http://127.0.0.1:8003/query `
  --levels 1,10,50 `
  --reqs 10
```

Load lớn hơn:

```powershell
.\.venv\Scripts\python.exe scripts\load_test.py `
  --url http://127.0.0.1:8003/query `
  --levels 1,10,50,100 `
  --reqs 20
```

Đọc output:

- `CCU`: số user đồng thời mô phỏng
- `ok`: request thành công
- `err`: request lỗi
- `p50`, `p95`, `p99`: latency percentile
- `qps`: request per second

Lưu ý: load test local không đại diện trực tiếp cho production khi cold path gọi OpenAI embeddings. Production cần benchmark riêng theo quota, region, cache hit rate và traffic shape thật.

### Drift test

```powershell
.\.venv\Scripts\python.exe scripts\drift_test.py
```

Script tạo `data/docs/drift_test_doc.md`, chạy CocoIndex và Graphify song song, sau đó in:

- thời gian CocoIndex incremental
- thời gian Graphify incremental
- drift window giữa hai pipeline

## Đổi embedding model và reindex

### OpenAI large

Trong `.env`:

```env
EMBED_PROVIDER=openai
EMBED_MODEL=text-embedding-3-large
EMBED_DIMENSIONS=3072
```

Rebuild:

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m indexing.flow drop
.\.venv\Scripts\python.exe -m indexing.flow update
```

Restart API rồi kiểm tra:

```powershell
Invoke-RestMethod http://127.0.0.1:8003/health
```

Kỳ vọng:

```text
model                 openai:text-embedding-3-large:3072
embedding_dimensions  3072
```

### OpenAI small

Trong `.env`:

```env
EMBED_PROVIDER=openai
EMBED_MODEL=text-embedding-3-small
EMBED_DIMENSIONS=1536
```

Rebuild và restart API tương tự. Kỳ vọng health trả:

```text
model                 openai:text-embedding-3-small:1536
embedding_dimensions  1536
```

### Local fallback

Trong `.env`:

```env
EMBED_PROVIDER=sentence_transformers
EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBED_DIMENSIONS=384
```

Dùng fallback này khi cần test offline hoặc không muốn gọi OpenAI API. Nếu dimension thay đổi so với DB hiện tại, vẫn cần `drop` và `update`.

### Test reindex tự động

`scripts/reindex_test.py` chạy full cycle cho từng model: `drop` + `update` rồi assert DB có đúng `vector_dims` và `model_name`. Đây là bằng chứng e2e cho khả năng reindex.

```powershell
.\.venv\Scripts\python.exe scripts\reindex_test.py `
  --models text-embedding-3-small:1536,text-embedding-3-large:3072 `
  --out reports\reindex_test.json
```

Lưu ý: mỗi model rebuild toàn bộ index và gọi embedding provider (tốn token). Script kết thúc với `RESULT: ALL PASSED` và để DB ở model cuối trong danh sách.

Mức unit (rẻ, không cần DB/OpenAI): `tests/test_embedding_config.py` assert `memo_key`/`model_name_for_storage` đổi khi model đổi và ổn định khi config y nguyên — chính là cơ chế trigger reindex của CocoIndex.

## Troubleshooting

### `ModuleNotFoundError: No module named 'indexing'` hoặc `No module named 'api'`

Set lại `PYTHONPATH` trong terminal hiện tại:

```powershell
$env:PYTHONPATH="src"
```

### API vẫn hiện model cũ sau khi sửa `.env`

Restart Uvicorn. API đọc config lúc process start.

### Vector dimension mismatch

Nguyên nhân thường là DB còn vector cũ nhưng API/query dùng model mới.

Fix POC:

```powershell
.\.venv\Scripts\python.exe -m indexing.flow drop
.\.venv\Scripts\python.exe -m indexing.flow update
```

Sau đó restart API.

### Không connect được Postgres

Kiểm tra `.env`:

```powershell
Get-Content .env | Select-String "POSTGRES_URL","PG_CONN"
```

Kiểm tra container/service Postgres:

```powershell
docker ps
```

### Graph hits rỗng

Chạy lại Graphify:

```powershell
.\.venv\Scripts\graphify.exe update data/docs
```

Kiểm tra `data/docs/graphify-out/graph.json` tồn tại và không rỗng.

### Port `8003` đang bận

Chạy port khác:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.retrieval:app --host 127.0.0.1 --port 8004
```

Sau đó đổi URL query/eval/load sang `http://127.0.0.1:8004`.

### Không muốn lộ API key khi demo

Chỉ in `.env` với key đã che:

```powershell
Get-Content .env | ForEach-Object {
  if ($_ -match '^OPENAI_API_KEY=') { 'OPENAI_API_KEY=<redacted>' } else { $_ }
}
```

## Giới hạn hiện tại

Đây là POC kỹ thuật, chưa phải production deployment.

Các giới hạn chính:

- Cache hiện là in-memory (đã thread-safe bằng lock cho concurrent load), nhưng chưa share giữa nhiều API replicas; production nên dùng cache ngoài như Redis.
- `graph.json` phù hợp POC; graph lớn nên cân nhắc Neo4j, Kuzu hoặc graph snapshot có version.
- OpenAI embedding API là external bottleneck ở cold path.
- pgvector production cần HNSW/IVFFlat tuning khi corpus lớn.
- Rule reranker là baseline deterministic; production nên thêm cross-encoder reranker sau khi có golden dataset đủ lớn.
- Strategy B tạo drift giữa vector và graph pipeline; production cần drift monitoring và degrade behavior rõ ràng.

## Bài học rút ra

1. Reindexability không chỉ là chạy lại embedding. Nếu đổi dimension, schema vector cũng phải được xử lý.
2. CocoIndex phù hợp phần incremental indexing vì giữ được target state, memoization và lifecycle update/drop/live rõ ràng.
3. Graphify hữu ích khi graph evidence trả về relation, confidence và source; nếu chỉ trả label node thì giá trị với LLM thấp hơn nhiều.
4. Generated artifacts như `graphify-out/**` phải bị exclude khỏi vector corpus, nếu không hệ thống sẽ tự index report của chính nó.
5. Chunk metadata là nền tảng của RAG tốt: `section_title`, `page_number`, `chunk_hash` giúp ranking, citation và debug dễ hơn.
6. Raw vector top-k dễ bị duplicate chiếm chỗ; dedupe nên là bước mặc định trong retrieval.
7. Heading của section có ảnh hưởng lớn đến embedding. Prepend `Section: <title>` giúp query theo chủ đề tìm đúng đoạn hơn.
8. Rule rerank đơn giản vẫn có giá trị nếu được đặt sau vector overfetch và được kiểm chứng bằng report.
9. Hai pipeline song song giảm blast radius nhưng tạo consistency drift; drift phải đo được, không nên chỉ giả định.
10. Load test local chỉ chứng minh behavior của POC trong máy hiện tại; production cần test lại với quota, cache, DB index và traffic thật.
11. Một RAG demo đáng tin cần cả code, metrics, report, tests và hướng dẫn vận hành. Chỉ có endpoint chạy được là chưa đủ.
