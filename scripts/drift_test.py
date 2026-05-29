"""Drift window test: thêm 1 file mới, đo cocoindex vs graphify pickup latency.

Cả 2 chạy ở incremental mode (batch update). Đo:
  - dt_cocoindex: thời gian từ file write -> cocoindex update kết thúc
  - dt_graphify:  thời gian từ file write -> graphify update kết thúc
  - drift = abs(dt_cocoindex - dt_graphify)

Đây là worst-case khi cả 2 chạy đồng thời sau khi file ghi.
Trong production: drift đo bằng pickup latency của live mode (rất nhỏ hơn).
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "data" / "docs"
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
GRAPHIFY_EXE = ROOT / ".venv" / "Scripts" / "graphify.exe"


NEW_FILE = DOCS / "drift_test_doc.md"
NEW_CONTENT = """# Drift Test Document

Tài liệu này được tạo để đo drift window giữa cocoindex và graphify.

## Nội dung kiểm tra
- Cocoindex sẽ embed nội dung này và lưu vào pgvector.
- Graphify sẽ extract entities và update graph.json.
- Drift = chênh lệch thời gian 2 pipeline xử lý xong.
"""


async def run_cocoindex() -> float:
    env = os.environ.copy()
    env.update({
        "POSTGRES_URL": "postgresql://postgres:ragpass@localhost:5433/ragdb",
        "EMBED_PROVIDER": os.getenv("EMBED_PROVIDER", "openai"),
        "EMBED_MODEL": os.getenv("EMBED_MODEL", "text-embedding-3-large"),
        "EMBED_DIMENSIONS": os.getenv("EMBED_DIMENSIONS", "3072"),
        "COCOINDEX_DB": str(ROOT / ".cocoindex"),
        "PYTHONPATH": "src",
    })
    t0 = time.perf_counter()
    proc = await asyncio.create_subprocess_exec(
        str(VENV_PY), "-m", "indexing.flow", "update",
        cwd=str(ROOT),
        env=env,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    return time.perf_counter() - t0


async def run_graphify() -> float:
    t0 = time.perf_counter()
    proc = await asyncio.create_subprocess_exec(
        str(GRAPHIFY_EXE), "update", "data/docs",
        cwd=str(ROOT),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    return time.perf_counter() - t0


def format_result_lines(dt_cocoindex: float, dt_graphify: float) -> list[str]:
    drift = abs(dt_cocoindex - dt_graphify)
    return [
        "",
        "=== RESULTS ===",
        f"  Cocoindex incremental:  {dt_cocoindex:.2f}s",
        f"  Graphify  incremental:  {dt_graphify:.2f}s",
        f"  Drift window:           {drift:.2f}s",
        "  (worst-case batch mode; live mode is expected to be lower)",
    ]


async def main() -> None:
    if NEW_FILE.exists():
        NEW_FILE.unlink()
    print(f"[drift] Writing new file: {NEW_FILE.name}")
    NEW_FILE.write_text(NEW_CONTENT, encoding="utf-8")
    t_write = time.perf_counter()

    print("[drift] Triggering cocoindex + graphify in parallel...")
    dt_co_task = asyncio.create_task(run_cocoindex())
    dt_gf_task = asyncio.create_task(run_graphify())
    dt_co, dt_gf = await asyncio.gather(dt_co_task, dt_gf_task)

    for line in format_result_lines(dt_co, dt_gf):
        print(line)


if __name__ == "__main__":
    asyncio.run(main())
