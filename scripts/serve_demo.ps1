<#
.SYNOPSIS
  Khoi dong demo Reindexable Hybrid RAG bang mot lenh.
.DESCRIPTION
  Kiem tra Postgres -> build vector index + graph neu thieu -> start FastAPI demo
  tai http://127.0.0.1:<Port>/demo. Mac dinh la incremental: KHONG drop index dang
  chay; chi rebuild khi truyen -Rebuild (giu nguyen thiet ke an toan cua POC).
.EXAMPLE
  .\scripts\serve_demo.ps1
.EXAMPLE
  .\scripts\serve_demo.ps1 -Rebuild -Port 8004
.EXAMPLE
  .\scripts\serve_demo.ps1 -SkipBuild   # chi start API, khong dung toi index/graph
#>
[CmdletBinding()]
param(
  [int]$Port = 8003,
  [switch]$Rebuild,
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

# --- Paths ---
$Root        = Split-Path -Parent $PSScriptRoot
$VenvPy      = Join-Path $Root ".venv\Scripts\python.exe"
$GraphifyExe = Join-Path $Root ".venv\Scripts\graphify.exe"
$GraphJson   = Join-Path $Root "data\docs\graphify-out\graph.json"
$DocsDir     = Join-Path $Root "data\docs"

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

if (-not (Test-Path $VenvPy)) {
  Write-Error "Khong tim thay venv python: $VenvPy. Tao venv truoc (xem README muc 'Cai dat')."
}

Set-Location $Root
$env:PYTHONPATH = "src"

# --- 1. Postgres ---
# Doc host/port tu .env POSTGRES_URL neu co, mac dinh 127.0.0.1:5433.
$PgHost = "127.0.0.1"
$PgPort = 5433
$envFile = Join-Path $Root ".env"
if (Test-Path $envFile) {
  $line = Select-String -Path $envFile -Pattern '^\s*POSTGRES_URL\s*=' | Select-Object -First 1
  if ($line -and $line.Line -match '@([^:/@]+):(\d+)/') {
    $PgHost = $Matches[1]
    $PgPort = [int]$Matches[2]
  }
}

function Test-Pg {
  (Test-NetConnection -ComputerName $PgHost -Port $PgPort -WarningAction SilentlyContinue).TcpTestSucceeded
}

Write-Step "Kiem tra Postgres tai ${PgHost}:${PgPort}"
if (-not (Test-Pg)) {
  Write-Host "Postgres chua phan hoi. Thu 'docker start rag-pgvector'..." -ForegroundColor Yellow
  $docker = Get-Command docker -ErrorAction SilentlyContinue
  if ($docker) {
    try { docker start rag-pgvector | Out-Null } catch { Write-Host "docker start that bai: $_" -ForegroundColor Yellow }
    for ($i = 0; $i -lt 30; $i++) {
      if (Test-Pg) { break }
      Start-Sleep -Milliseconds 500
    }
  }
  if (-not (Test-Pg)) {
    Write-Error "Khong ket noi duoc Postgres ${PgHost}:${PgPort}. Khoi dong Postgres roi chay lai (README muc 'Yeu cau moi truong')."
  }
}
Write-Host "Postgres OK." -ForegroundColor Green

# --- 2. Vector index (CocoIndex) ---
if ($SkipBuild) {
  Write-Step "Bo qua build (-SkipBuild)"
} else {
  if ($Rebuild) {
    Write-Step "Rebuild vector index (drop + update)"
    & $VenvPy -m indexing.flow drop
    & $VenvPy -m indexing.flow update
  } else {
    $countRaw = & $VenvPy -c @'
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
    import psycopg
    url = os.getenv("PG_CONN") or os.getenv("POSTGRES_URL")
    with psycopg.connect(url, connect_timeout=5) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM rag.doc_chunks")
        print(cur.fetchone()[0])
except Exception:
    print(-1)
'@
    $count = ($countRaw | Select-Object -Last 1).ToString().Trim()
    if ($count -eq "0" -or $count -eq "-1") {
      Write-Step "Vector index trong/chua co (count=$count) -> indexing.flow update"
      & $VenvPy -m indexing.flow update
    } else {
      Write-Host "Vector index da co $count chunks, bo qua (dung -Rebuild de build lai)." -ForegroundColor Green
    }
  }

  # --- 3. Graph (Graphify) ---
  if ($Rebuild -or -not (Test-Path $GraphJson)) {
    if (Test-Path $GraphifyExe) {
      Write-Step "Build graph bang Graphify"
      & $GraphifyExe update $DocsDir
    } else {
      Write-Host "Khong tim thay graphify.exe, bo qua build graph (graph evidence se rong)." -ForegroundColor Yellow
    }
  } else {
    Write-Host "graph.json da co, bo qua (dung -Rebuild de build lai)." -ForegroundColor Green
  }
}

# --- 4. Start API ---
Write-Step "Khoi dong API: http://127.0.0.1:$Port/demo   (Ctrl+C de dung)"
& $VenvPy -m uvicorn api.retrieval:app --host 127.0.0.1 --port $Port
