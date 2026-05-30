"""End-to-end reindex test: rebuild the vector index for each embedding model
and assert the DB reflects the new dimension + model_name.

This proves the project's core thesis (reindexable on model change): switching
EMBED_MODEL/EMBED_DIMENSIONS and running drop+update must rebuild the pgvector
index so its stored dimension and model_name match the new config.

WARNING: each model rebuilds the whole index, which calls the embedding provider
(OpenAI for text-embedding-* models) and costs tokens. Keep the model list small.

Usage:
  python scripts/reindex_test.py
  python scripts/reindex_test.py --models text-embedding-3-small:1536,text-embedding-3-large:3072
  python scripts/reindex_test.py --out reports/reindex_test.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _db_state() -> dict[str, Any]:
    """Return the vector dims + model_names + row count currently in the DB."""
    sys.path.insert(0, str(SRC))
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    import psycopg

    url = os.getenv("PG_CONN") or os.getenv("POSTGRES_URL")
    with psycopg.connect(url, connect_timeout=10) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM rag.doc_chunks")
        rows = cur.fetchone()[0]
        cur.execute("SELECT DISTINCT vector_dims(embedding) FROM rag.doc_chunks")
        dims = sorted(r[0] for r in cur.fetchall())
        cur.execute("SELECT DISTINCT model_name FROM rag.doc_chunks")
        models = sorted(r[0] for r in cur.fetchall() if r[0])
    return {"rows": rows, "dims": dims, "models": models}


def _run_flow(mode: str, env: dict[str, str]) -> None:
    """Run `python -m indexing.flow <mode>` with the given embedding env."""
    result = subprocess.run(
        [sys.executable, "-m", "indexing.flow", mode],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        # cocoindex prints emoji/ANSI; force UTF-8 so the parent never trips on
        # the Windows console codepage (cp1258) when decoding child output.
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        sys.stderr.write(result.stdout[-2000:])
        sys.stderr.write(result.stderr[-2000:])
        raise RuntimeError(f"indexing.flow {mode} failed (exit {result.returncode})")


def reindex_to(provider: str, model: str, dimensions: int) -> dict[str, Any]:
    env = dict(os.environ)
    env["PYTHONPATH"] = "src"
    env["EMBED_PROVIDER"] = provider
    env["EMBED_MODEL"] = model
    env["EMBED_DIMENSIONS"] = str(dimensions)

    started = time.perf_counter()
    _run_flow("drop", env)
    _run_flow("update", env)
    elapsed_ms = (time.perf_counter() - started) * 1000

    expected_model = f"{provider}:{model}:{dimensions}"
    state = _db_state()
    dims_ok = state["dims"] == [dimensions]
    model_ok = state["models"] == [expected_model]
    return {
        "provider": provider,
        "model": model,
        "dimensions": dimensions,
        "expected_model_name": expected_model,
        "db_rows": state["rows"],
        "db_dims": state["dims"],
        "db_models": state["models"],
        "dims_ok": dims_ok,
        "model_ok": model_ok,
        "passed": dims_ok and model_ok and state["rows"] > 0,
        "reindex_ms": round(elapsed_ms, 1),
    }


def parse_models(spec: str) -> list[tuple[str, int]]:
    pairs: list[tuple[str, int]] = []
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        model, _, dim = item.rpartition(":")
        if not model or not dim.isdigit():
            raise ValueError(f"Bad --models entry {item!r}; expected model:dim")
        pairs.append((model, int(dim)))
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        default="text-embedding-3-small:1536,text-embedding-3-large:3072",
        help="Comma-separated model:dim list to reindex through, in order.",
    )
    parser.add_argument("--provider", default="openai")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    models = parse_models(args.models)
    print(f"Reindex test across {len(models)} model(s): {models}")
    print("WARNING: each model rebuilds the index and calls the embedding provider.\n")

    results: list[dict[str, Any]] = []
    for model, dim in models:
        print(f"==> reindex to {args.provider}:{model}:{dim} (drop + update)")
        res = reindex_to(args.provider, model, dim)
        results.append(res)
        status = "PASS" if res["passed"] else "FAIL"
        print(
            f"    [{status}] db_dims={res['db_dims']} db_models={res['db_models']} "
            f"rows={res['db_rows']} ({res['reindex_ms']} ms)\n"
        )

    all_passed = all(r["passed"] for r in results)
    payload = {"all_passed": all_passed, "results": results}
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote {args.out}")

    print("RESULT:", "ALL PASSED" if all_passed else "FAILED")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
