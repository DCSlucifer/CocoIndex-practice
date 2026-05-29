"""Deterministic retrieval dedupe and lightweight reranking helpers."""
from __future__ import annotations

import re
from dataclasses import dataclass, replace


STOP_WORDS = {
    "about",
    "after",
    "and",
    "are",
    "for",
    "from",
    "how",
    "into",
    "is",
    "of",
    "the",
    "this",
    "that",
    "what",
    "when",
    "where",
    "which",
    "why",
    "with",
}


@dataclass(frozen=True)
class RetrievalCandidate:
    source_path: str
    text: str
    vector_score: float
    chunk_hash: str | None = None
    section_title: str | None = None
    page_number: int | None = None
    rerank_score: float | None = None


def normalize_chunk_text(text: str) -> str:
    return " ".join(text.casefold().split())


def _tokenize(text: str) -> set[str]:
    tokens = set(re.findall(r"[a-z0-9]+", text.casefold()))
    compact = {
        re.sub(r"[-_\s/]+", "", term)
        for term in re.findall(r"[a-z0-9]+(?:[-_/]+[a-z0-9]+)+", text.casefold())
    }
    return {token for token in tokens | compact if len(token) > 2 and token not in STOP_WORDS}


def _dedupe_key(candidate: RetrievalCandidate) -> str:
    if candidate.chunk_hash:
        return candidate.chunk_hash
    return normalize_chunk_text(candidate.text)


def dedupe_candidates(candidates: list[RetrievalCandidate]) -> list[RetrievalCandidate]:
    best_by_key: dict[str, tuple[int, RetrievalCandidate]] = {}
    for index, candidate in enumerate(candidates):
        key = _dedupe_key(candidate)
        existing = best_by_key.get(key)
        if existing is None or candidate.vector_score > existing[1].vector_score:
            first_index = index if existing is None else existing[0]
            best_by_key[key] = (first_index, candidate)

    return [
        candidate
        for _, candidate in sorted(best_by_key.values(), key=lambda item: item[0])
    ]


def rule_rerank(query: str, candidates: list[RetrievalCandidate]) -> list[RetrievalCandidate]:
    query_terms = _tokenize(query)
    reranked: list[RetrievalCandidate] = []
    for candidate in candidates:
        text_terms = _tokenize(candidate.text)
        section_terms = _tokenize(candidate.section_title or "")
        section_overlap = len(query_terms & section_terms)
        text_overlap = len(query_terms & text_terms)
        section_phrase_bonus = 0.0
        if candidate.section_title:
            section_title = candidate.section_title.casefold()
            for term in query_terms:
                if len(term) > 4 and term in section_title:
                    section_phrase_bonus += 0.03

        rerank_score = (
            candidate.vector_score
            + section_overlap * 0.06
            + text_overlap * 0.01
            + section_phrase_bonus
        )
        reranked.append(replace(candidate, rerank_score=rerank_score))

    reranked.sort(
        key=lambda item: (
            -(item.rerank_score if item.rerank_score is not None else item.vector_score),
            -item.vector_score,
            item.source_path,
            item.chunk_hash or normalize_chunk_text(item.text),
        ),
    )
    return reranked
