# Demo Runbook — tất cả lệnh cần chạy

> Chạy trong **PowerShell**, tại thư mục gốc repo. Theo thứ tự từ trên xuống.
> Lý thuyết/giải thích xem [`core-guide.md`](core-guide.md).

```powershell
cd "D:\Rag vsf"
```

---

## Phase 0 — Một lần (bỏ qua nếu đã setup)

```powershell
# Tạo venv (nếu chưa có .venv)
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip

# Cài dependencies
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Tạo .env và điền OPENAI_API_KEY
Copy-Item .env.example .env
notepad .env
```

Đảm bảo Postgres (pgvector) chạy. Nếu dùng Docker:

```powershell
# Lần đầu (tạo container)
docker run --name rag-pgvector -e POSTGRES_PASSWORD=ragpass -e POSTGRES_DB=ragdb -p 5433:5432 -d pgvector/pgvector:pg16

# Các lần sau (container đã có)
docker start rag-pgvector
```

---

## Phase 1 — Khởi động (cách nhanh nhất: 1 lệnh)

```powershell
.\scripts\serve_demo.ps1
```

Script tự: kiểm tra/khởi động Postgres → build index + graph nếu thiếu (incremental, **không** drop) → start API tại `http://127.0.0.1:8003`.

Tùy chọn:

```powershell
.\scripts\serve_demo.ps1 -Rebuild     # drop + build lại từ đầu
.\scripts\serve_demo.ps1 -Port 8004   # đổi port
.\scripts\serve_demo.ps1 -SkipBuild   # chỉ start API
```

> Cửa sổ này sẽ "treo" vì uvicorn đang chạy. **Mở PowerShell thứ 2** cho các lệnh ở phase sau. Dừng API bằng `Ctrl+C`.

### (Tuỳ chọn) Khởi động thủ công từng bước — để giảng giải với mentor

```powershell
# Terminal mọi lệnh Python cần:
$env:PYTHONPATH="src"

# 1) Build vector index bằng CocoIndex
.\.venv\Scripts\python.exe -m indexing.flow update

# 2) Build graph bằng Graphify
.\.venv\Scripts\graphify.exe update data/docs

# 3) Start API
.\.venv\Scripts\python.exe -m uvicorn api.retrieval:app --host 127.0.0.1 --port 8003
```

---

## Phase 2 — Mở UI + kiểm tra sức khoẻ

```powershell
# Mở UI trong browser
Start-Process "http://127.0.0.1:8003/demo"

# Health check (terminal 2)
Invoke-RestMethod http://127.0.0.1:8003/health
```

Kỳ vọng: `ok=True`, `index_ready=True`, `model=openai:text-embedding-3-large:3072`, `graph_nodes>0`.

Trên UI: bấm câu hỏi mẫu → **Ask RAG**. Xem Answer + Citations + Vector Evidence (badge `graph ✓/✗`) + Graph Evidence + Timing. Tick **Evidence only (no LLM)** để demo `/query` không tốn LLM.

---

## Phase 3 — Gọi API thủ công (terminal 2)

```powershell
$body = @{ question = "How does the system reindex when embedding model changes?"; top_k = 5; graph_depth = 1 } | ConvertTo-Json
```

### Query (vector + graph evidence, không LLM)

```powershell
$r = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8003/query" -ContentType "application/json" -Body $body

$r.timing_ms
$r.vector_hits | Select-Object source_path, section_title, page_number, vector_score, rerank_score, graph_known
$r.graph_hits  | Select-Object confidence, relation, source_file, distance
$r.graph_known_doc_filter_applied
```

### Answer (có citations, gọi LLM)

```powershell
$a = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8003/answer" -ContentType "application/json" -Body $body

$a.answer
$a.citations | Select-Object id, source_name, section_title, page_number
$a | Select-Object model, retrieval_model, cached
```

---

## Phase 4 — Demo reindex (điểm nhấn)

Mục tiêu: chứng minh đổi model → reindex → hệ chạy với model mới. Đây cũng minh hoạt guard ở `/health`.

```powershell
$env:PYTHONPATH="src"

# (A) Đổi sang model nhỏ hơn để thấy sự khác biệt: sửa .env
#     EMBED_MODEL=text-embedding-3-small
#     EMBED_DIMENSIONS=1536
notepad .env

# (B) Trước khi reindex, nếu restart API ngay -> /health báo mismatch:
#     index_ready=false + warnings (DB dim != config dim)

# (C) Reindex (đổi dimension => bắt buộc drop trước)
.\.venv\Scripts\python.exe -m indexing.flow drop
.\.venv\Scripts\python.exe -m indexing.flow update

# (D) Restart API (Ctrl+C ở terminal API rồi chạy lại), kiểm tra flip:
Invoke-RestMethod http://127.0.0.1:8003/health   # index_ready=True, dims=1536
```

### Reindex tự động (build qua nhiều model + assert DB)

```powershell
.\.venv\Scripts\python.exe scripts\reindex_test.py `
  --models text-embedding-3-small:1536,text-embedding-3-large:3072 `
  --out reports\reindex_test.json
```

> Lưu ý chi phí: mỗi model rebuild toàn bộ index = gọi OpenAI (tốn token, nhỏ). Script kết thúc `RESULT: ALL PASSED`, để DB ở model cuối danh sách.

---

## Phase 5 — Test, evaluation, đo đạc (tuỳ chọn)

```powershell
# Unit tests (gồm test cơ chế reindex memo_key) — không cần API/DB
.\.venv\Scripts\python.exe -m unittest discover -s tests

# Compile check
.\.venv\Scripts\python.exe -m compileall -q src scripts tests

# Retrieval evaluation (cần API đang chạy)
.\.venv\Scripts\python.exe scripts\evaluate_retrieval.py --url http://127.0.0.1:8003/query --out reports\retrieval_eval_optimized.json

# Load test cục bộ (cần API đang chạy)
.\.venv\Scripts\python.exe scripts\load_test.py --url http://127.0.0.1:8003/query --levels 1,10,50 --reqs 10

# Drift test CocoIndex vs Graphify
.\.venv\Scripts\python.exe scripts\drift_test.py
```

---

## Phase 6 — Dừng / dọn

```powershell
# Dừng API: Ctrl+C ở terminal đang chạy uvicorn. Nếu chạy nền, kill theo port:
Get-NetTCPConnection -LocalPort 8003 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }

# (Tuỳ chọn) dừng Postgres
docker stop rag-pgvector
```

---

## Thứ tự tối thiểu để demo nhanh

```powershell
cd "D:\Rag vsf"
docker start rag-pgvector
.\scripts\serve_demo.ps1
# terminal 2:
Start-Process "http://127.0.0.1:8003/demo"
Invoke-RestMethod http://127.0.0.1:8003/health
```

Sau đó thao tác trực tiếp trên UI. Xong thì `Ctrl+C`.
