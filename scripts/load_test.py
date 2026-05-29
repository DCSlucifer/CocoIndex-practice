"""Load test: gia lap N CCU concurrent goi /query.

Do: p50/p95/p99 latency, throughput, error rate.
Khong dung tieng Viet trong stdout de tranh CP1258 encoding issue tren PowerShell.
"""
from __future__ import annotations

import argparse
import asyncio
import random
import statistics
import time
from dataclasses import dataclass

import httpx


DEFAULT_URL = "http://127.0.0.1:8000/query"

QUERIES = [
    "How does the system reindex when embedding model changes?",
    "What confidence tags does graphify use on edges?",
    "What does the HybridRetriever class do?",
    "Explain the cocoindex incremental processing",
    "How is the knowledge graph built from code?",
    "Which embedding models are recommended for production?",
    "What is Leiden community detection used for?",
    "How does pgvector store embeddings?",
    "What is the difference between EXTRACTED and INFERRED edges?",
    "Why use hybrid retrieval (vector + graph)?",
    "What sources does cocoindex support?",
    "How does the watch mode work in graphify?",
    "Explain the doc_id reconciliation strategy",
    "What are god nodes in graphify?",
    "How is the embedding column dimension determined?",
]


@dataclass
class Result:
    latency_ms: float
    ok: bool
    status: int


async def one_request(client: httpx.AsyncClient, url: str) -> Result:
    q = random.choice(QUERIES)
    body = {"question": q, "top_k": 5}
    t0 = time.perf_counter()
    try:
        r = await client.post(url, json=body, timeout=30.0)
        latency = (time.perf_counter() - t0) * 1000
        return Result(latency_ms=latency, ok=r.status_code == 200, status=r.status_code)
    except Exception:
        latency = (time.perf_counter() - t0) * 1000
        return Result(latency_ms=latency, ok=False, status=0)


async def worker(client: httpx.AsyncClient, url: str, n: int, out: list[Result]) -> None:
    for _ in range(n):
        out.append(await one_request(client, url))


async def warmup_queries(client: httpx.AsyncClient, url: str) -> None:
    for query in QUERIES:
        try:
            await client.post(url, json={"question": query, "top_k": 5}, timeout=30.0)
        except Exception:
            pass


async def run(url: str, ccu: int, total_per_user: int, warmup: bool) -> None:
    results: list[Result] = []
    async with httpx.AsyncClient(http2=False) as client:
        if warmup:
            await warmup_queries(client, url)
        else:
            await one_request(client, url)
        t0 = time.perf_counter()
        tasks = [worker(client, url, total_per_user, results) for _ in range(ccu)]
        await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - t0

    lats = sorted(r.latency_ms for r in results if r.ok)
    errs = sum(1 for r in results if not r.ok)
    total = len(results)
    if not lats:
        print(f"CCU={ccu:>3} | ALL FAILED ({errs}/{total})")
        return

    def pct(p: float) -> float:
        return lats[min(int(len(lats) * p), len(lats) - 1)]

    print(
        f"CCU={ccu:>3} | reqs={total:>4} ok={total - errs:>4} err={errs:>3} | "
        f"p50={pct(0.5):>6.1f}ms  p95={pct(0.95):>6.1f}ms  p99={pct(0.99):>6.1f}ms  "
        f"avg={statistics.mean(lats):>6.1f}ms | "
        f"qps={total / elapsed:>5.1f}"
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--levels", type=str, default="1,10,50,100")
    parser.add_argument("--reqs", type=int, default=20, help="requests per user")
    parser.add_argument("--url", type=str, default=DEFAULT_URL)
    parser.add_argument("--cold", action="store_true", help="Skip full query warmup.")
    args = parser.parse_args()

    print(f"Load test: url={args.url} reqs_per_user={args.reqs} warmup={not args.cold}")
    print("=" * 100)
    for ccu in [int(x) for x in args.levels.split(",")]:
        await run(args.url, ccu, args.reqs, warmup=not args.cold)


if __name__ == "__main__":
    asyncio.run(main())
