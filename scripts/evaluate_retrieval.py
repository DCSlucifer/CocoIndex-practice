"""Evaluate vector-only vs vector+graph evidence for the demo RAG service."""
from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx


DEFAULT_URL = "http://127.0.0.1:8000/query"


CASES = [
    {
        "id": "reindex_model_change",
        "question": "How does the system reindex when embedding model changes?",
        "expected_sources": ["cocoindex_intro.md", "embedding_models.md", "rag_paper_intro.pdf"],
        "expected_graph_labels": ["Re-index", "Embedding Models"],
    },
    {
        "id": "graphify_confidence",
        "question": "What confidence tags does graphify use on edges?",
        "expected_sources": ["graphify_intro.md", "rag_paper_intro.pdf"],
        "expected_graph_labels": ["Confidence Tags", "Graphify Knowledge Graph Builder"],
    },
    {
        "id": "hybrid_code_path",
        "question": "What does HybridRetriever connect between VectorStore and GraphStore?",
        "expected_sources": ["sample_code.py"],
        "expected_graph_labels": ["HybridRetriever", "VectorStore", "GraphStore"],
    },
    {
        "id": "incremental_processing",
        "question": "Explain cocoindex incremental processing for RAG freshness",
        "expected_sources": ["cocoindex_intro.md", "rag_long_whitepaper.pdf"],
        "expected_graph_labels": ["Cơ chế Incremental", "Cocoindex Engine Overview"],
    },
    {
        "id": "strategy_b",
        "question": "Why use Strategy B with two parallel pipelines?",
        "expected_sources": ["rag_architecture.md"],
        "expected_graph_labels": ["RAG Architecture: Strategy B", "Hybrid Retrieval"],
    },
]


@dataclass
class CaseResult:
    id: str
    question: str
    latency_ms: float
    vector_ok: bool
    graph_ok: bool
    confidence_ok: bool
    vector_only_score: int
    hybrid_score: int
    vector_sources: list[str]
    graph_labels: list[str]
    graph_confidences: list[str]


def _contains_any(value: str, expected: list[str]) -> bool:
    value_l = value.casefold()
    return any(item.casefold() in value_l for item in expected)


def evaluate_case(client: httpx.Client, url: str, case: dict[str, Any]) -> CaseResult:
    started = time.perf_counter()
    response = client.post(
        url,
        json={"question": case["question"], "top_k": 5, "graph_depth": 1},
        timeout=30.0,
    )
    response.raise_for_status()
    latency_ms = (time.perf_counter() - started) * 1000
    data = response.json()

    vector_sources = [hit["source_path"] for hit in data["vector_hits"]]
    graph_labels = [
        str(hit.get("node", {}).get("label") or hit.get("node", {}).get("id") or "")
        for hit in data["graph_hits"]
    ]
    graph_confidences = [
        str(hit.get("confidence"))
        for hit in data["graph_hits"]
        if hit.get("confidence")
    ]

    vector_ok = any(_contains_any(source, case["expected_sources"]) for source in vector_sources)
    graph_ok = any(_contains_any(label, case["expected_graph_labels"]) for label in graph_labels)
    confidence_ok = any(conf in {"EXTRACTED", "INFERRED", "AMBIGUOUS"} for conf in graph_confidences)
    vector_only_score = int(vector_ok)
    hybrid_score = int(vector_ok) + int(graph_ok) + int(confidence_ok)

    return CaseResult(
        id=case["id"],
        question=case["question"],
        latency_ms=latency_ms,
        vector_ok=vector_ok,
        graph_ok=graph_ok,
        confidence_ok=confidence_ok,
        vector_only_score=vector_only_score,
        hybrid_score=hybrid_score,
        vector_sources=vector_sources,
        graph_labels=graph_labels,
        graph_confidences=graph_confidences,
    )


def summarize(results: list[CaseResult]) -> dict[str, Any]:
    latencies = [result.latency_ms for result in results]
    return {
        "cases": len(results),
        "vector_source_recall": sum(result.vector_ok for result in results) / len(results),
        "graph_evidence_recall": sum(result.graph_ok for result in results) / len(results),
        "confidence_tag_recall": sum(result.confidence_ok for result in results) / len(results),
        "avg_vector_only_score": statistics.mean(result.vector_only_score for result in results),
        "avg_hybrid_score": statistics.mean(result.hybrid_score for result in results),
        "p50_latency_ms": statistics.median(latencies),
        "max_latency_ms": max(latencies),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    with httpx.Client() as client:
        results = [evaluate_case(client, args.url, case) for case in CASES]
    payload = {
        "url": args.url,
        "summary": summarize(results),
        "results": [asdict(result) for result in results],
    }

    print(json.dumps(payload["summary"], indent=2, ensure_ascii=False))
    for result in results:
        print(
            f"{result.id}: vector_ok={result.vector_ok} "
            f"graph_ok={result.graph_ok} confidence_ok={result.confidence_ok} "
            f"latency={result.latency_ms:.1f}ms"
        )

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
