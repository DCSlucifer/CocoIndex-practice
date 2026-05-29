"""Graphify graph helpers used by the retrieval API and tests."""
from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


STOP_WORDS = {
    "about",
    "after",
    "does",
    "from",
    "have",
    "into",
    "the",
    "this",
    "that",
    "what",
    "when",
    "where",
    "which",
    "with",
    "how",
    "why",
    "and",
    "for",
    "can",
    "are",
    "is",
    "to",
    "of",
    "a",
    "an",
}


def _fold_ascii(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def tokenize_for_graph(text: str) -> set[str]:
    """Tokenize text for graph matching, preserving useful compact terms.

    The compact pass turns terms like ``re-index`` and ``HybridRetriever`` into
    searchable forms such as ``reindex`` and ``hybridretriever``.
    """
    folded = _fold_ascii(text)
    compact_terms = {
        re.sub(r"[-_\s/]+", "", term)
        for term in re.findall(r"[a-z0-9]+(?:[-_/]+[a-z0-9]+)+", folded)
    }
    tokens = set(re.findall(r"[a-z0-9]+", folded)) | compact_terms
    return {token for token in tokens if len(token) > 1 and token not in STOP_WORDS}


@dataclass(frozen=True)
class NodeMatch:
    node_id: str
    node: dict[str, Any]
    score: float


@dataclass(frozen=True)
class GraphEvidence:
    node: dict[str, Any]
    distance: int
    relation: str | None = None
    confidence: str | None = None
    confidence_score: float | None = None
    source_file: str | None = None
    source_location: str | None = None
    seed: str | None = None


class GraphIndex:
    """Load graphify's graph.json and provide ranked neighbor expansion."""

    def __init__(self, path: Path):
        self.path = path
        self.nodes: dict[str, dict[str, Any]] = {}
        self.adj: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.known_source_files: set[str] = set()
        self.mtime: float = 0.0
        self._node_terms: dict[str, set[str]] = {}
        self._load()

    def _node_id(self, node: dict[str, Any]) -> str | None:
        return node.get("id") or node.get("name") or node.get("label")

    def _load(self) -> None:
        if not self.path.exists():
            return
        self.mtime = self.path.stat().st_mtime
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        for node in raw.get("nodes", []):
            node_id = self._node_id(node)
            if not node_id:
                continue
            self.nodes[node_id] = node
            source_file = node.get("source_file")
            if source_file:
                self.known_source_files.add(Path(str(source_file)).name)
            searchable = " ".join(
                str(node.get(key, ""))
                for key in ("id", "name", "label", "norm_label", "source_file")
            )
            self._node_terms[node_id] = tokenize_for_graph(searchable)

        edges = raw.get("edges") or raw.get("links") or []
        for edge in edges:
            source = edge.get("source") or edge.get("src")
            target = edge.get("target") or edge.get("dst")
            if not source or not target:
                continue
            self.adj[source].append({"to": target, "edge": edge})
            self.adj[target].append({"to": source, "edge": edge})
            source_file = edge.get("source_file")
            if source_file:
                self.known_source_files.add(Path(str(source_file)).name)

    def maybe_reload(self) -> None:
        if self.path.exists() and self.path.stat().st_mtime > self.mtime:
            self.nodes.clear()
            self.adj.clear()
            self.known_source_files.clear()
            self._node_terms.clear()
            self._load()

    def is_graph_known_source(self, source_path: str) -> bool:
        normalized = source_path.replace("\\", "/")
        if "/graphify-out/" in f"/{normalized}":
            return False
        if not self.known_source_files:
            return True
        return Path(normalized).name in self.known_source_files

    def rank_nodes(
        self,
        query: str,
        context_texts: list[str],
        limit: int = 8,
    ) -> list[NodeMatch]:
        query_terms = tokenize_for_graph(query)
        context_terms: set[str] = set()
        for text in context_texts:
            context_terms.update(tokenize_for_graph(text))

        matches: list[NodeMatch] = []
        for node_id, node in self.nodes.items():
            terms = self._node_terms.get(node_id, set())
            query_overlap = query_terms & terms
            context_overlap = context_terms & terms
            score = len(query_overlap) * 3.0 + len(context_overlap)

            label = _fold_ascii(str(node.get("label", "")))
            compact_label = re.sub(r"[^a-z0-9]+", "", label)
            for term in query_terms:
                if len(term) > 3 and (term in label or term in compact_label):
                    score += 1.5

            if score > 0:
                matches.append(NodeMatch(node_id=node_id, node=node, score=score))

        matches.sort(
            key=lambda match: (
                -match.score,
                str(match.node.get("source_file", "")),
                str(match.node.get("label", "")),
            )
        )
        return matches[:limit]

    def expand_for_query(
        self,
        query: str,
        context_texts: list[str],
        top_k: int,
        depth: int,
    ) -> list[GraphEvidence]:
        seeds = self.rank_nodes(query, context_texts, limit=max(4, top_k))
        results: list[GraphEvidence] = []
        seen: set[str] = set()

        for seed in seeds:
            if seed.node_id not in seen:
                seen.add(seed.node_id)
                results.append(GraphEvidence(node=seed.node, distance=0, seed=seed.node_id))

            frontier = [seed.node_id]
            visited = {seed.node_id}
            for distance in range(1, max(1, depth) + 1):
                next_frontier: list[str] = []
                for node_id in frontier:
                    for item in self.adj.get(node_id, []):
                        target = item["to"]
                        if target in visited:
                            continue
                        visited.add(target)
                        next_frontier.append(target)
                        edge = item["edge"]
                        if target in seen:
                            continue
                        seen.add(target)
                        results.append(
                            GraphEvidence(
                                node=self.nodes.get(target, {"id": target}),
                                distance=distance,
                                relation=edge.get("relation"),
                                confidence=edge.get("confidence"),
                                confidence_score=edge.get("confidence_score"),
                                source_file=edge.get("source_file"),
                                source_location=edge.get("source_location"),
                                seed=seed.node_id,
                            )
                        )
                        if len(results) >= top_k:
                            return results
                frontier = next_frontier
        return results[:top_k]
