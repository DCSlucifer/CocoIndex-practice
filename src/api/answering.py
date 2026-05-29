"""Answer generation helpers for grounded RAG responses."""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import PureWindowsPath
from typing import Any, Mapping, Sequence

import httpx
from pydantic import BaseModel

from embedding_config import DEFAULT_OPENAI_BASE_URL


DEFAULT_ANSWER_MODEL = "gpt-4o-mini"


class Citation(BaseModel):
    id: int
    source_path: str
    source_name: str
    section_title: str | None = None
    page_number: int | None = None
    snippet: str


class AnswerResult(BaseModel):
    answer: str
    citations: list[Citation]
    model: str


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _snippet(text: str, *, limit: int = 320) -> str:
    compact = _compact(text)
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _source_name(source_path: str) -> str:
    return PureWindowsPath(source_path).name or source_path


def build_citations(vector_hits: Sequence[Any], *, max_citations: int = 5) -> list[Citation]:
    citations: list[Citation] = []
    seen: set[tuple[str, str | None, int | None]] = set()
    for hit in vector_hits:
        source_path = str(_field(hit, "source_path", "") or "")
        text = str(_field(hit, "chunk_text", _field(hit, "text", "")) or "")
        if not source_path or not text:
            continue
        section_title = _field(hit, "section_title")
        page_number = _field(hit, "page_number")
        key = (source_path, section_title, page_number)
        if key in seen:
            continue
        seen.add(key)
        citations.append(
            Citation(
                id=len(citations) + 1,
                source_path=source_path,
                source_name=_source_name(source_path),
                section_title=section_title,
                page_number=page_number,
                snippet=_snippet(text),
            )
        )
        if len(citations) >= max_citations:
            break
    return citations


def _format_citation(citation: Citation) -> str:
    location = []
    if citation.section_title:
        location.append(f"section={citation.section_title}")
    if citation.page_number is not None:
        location.append(f"page={citation.page_number}")
    location_text = f" ({'; '.join(location)})" if location else ""
    return f"[{citation.id}] {citation.source_name}{location_text}: {citation.snippet}"


def _format_graph_hit(hit: Any, index: int) -> str:
    node = _field(hit, "node", {}) or {}
    label = node.get("label") if isinstance(node, Mapping) else str(node)
    relation = _field(hit, "relation") or "related"
    confidence = _field(hit, "confidence") or "unknown"
    source = _field(hit, "source_file") or _field(hit, "source_path") or "unknown source"
    return f"{index}. {label} --{relation}--> confidence={confidence}, source={source}"


def build_answer_messages(
    question: str,
    citations: Sequence[Citation],
    graph_hits: Sequence[Any],
) -> list[dict[str, str]]:
    citation_text = "\n".join(_format_citation(citation) for citation in citations)
    graph_text = "\n".join(
        _format_graph_hit(hit, index)
        for index, hit in enumerate(graph_hits[:10], start=1)
    )
    if not graph_text:
        graph_text = "No graph evidence was retrieved."

    system = (
        "You are a grounded RAG answer generator. "
        "Use only the supplied evidence. "
        "Cite factual claims with citation markers like [1]. "
        "If the evidence is insufficient, say so directly."
    )
    user = (
        f"Question:\n{question}\n\n"
        f"Citation evidence:\n{citation_text}\n\n"
        f"Graph evidence:\n{graph_text}\n\n"
        "Write a concise answer for a technical demo. "
        "Mention the retrieval limitation if the evidence does not fully answer the question."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def fallback_answer(question: str) -> str:
    return (
        "I do not have enough retrieved evidence to answer this question safely: "
        f"{question}"
    )


class OpenAIChatClient:
    """Small OpenAI chat-completions client using httpx."""

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = DEFAULT_OPENAI_BASE_URL,
        model: str = DEFAULT_ANSWER_MODEL,
        organization: str | None = None,
        project: str | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.organization = organization
        self.project = project
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.transport = transport

    def _url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for answer generation")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.organization:
            headers["OpenAI-Organization"] = self.organization
        if self.project:
            headers["OpenAI-Project"] = self.project
        return headers

    def _payload(self, messages: Sequence[Mapping[str, str]]) -> bytes:
        payload = {
            "model": self.model,
            "messages": list(messages),
            "temperature": 0.2,
            "max_tokens": 700,
        }
        return json.dumps(payload, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout)):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code == 429 or exc.response.status_code >= 500
        return False

    async def complete(self, messages: Sequence[Mapping[str, str]]) -> str:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(
                    transport=self.transport,
                    timeout=self.timeout_seconds,
                ) as client:
                    response = await client.post(
                        self._url(),
                        content=self._payload(messages),
                        headers=self._headers(),
                    )
                response.raise_for_status()
                data = response.json()
                return str(data["choices"][0]["message"]["content"]).strip()
            except Exception as exc:
                last_exc = exc
                if attempt + 1 >= self.max_retries or not self._is_retryable(exc):
                    raise
                await asyncio.sleep(0.25 * (2**attempt))
        assert last_exc is not None
        raise last_exc


async def generate_answer(
    *,
    question: str,
    vector_hits: Sequence[Any],
    graph_hits: Sequence[Any],
    api_key: str | None,
    base_url: str = DEFAULT_OPENAI_BASE_URL,
    model: str = DEFAULT_ANSWER_MODEL,
    organization: str | None = None,
    project: str | None = None,
    timeout_seconds: float = 30.0,
    max_retries: int = 3,
) -> AnswerResult:
    citations = build_citations(vector_hits)
    if not citations:
        return AnswerResult(
            answer=fallback_answer(question),
            citations=[],
            model=model,
        )
    client = OpenAIChatClient(
        api_key=api_key,
        base_url=base_url,
        model=model,
        organization=organization,
        project=project,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )
    messages = build_answer_messages(question, citations, graph_hits)
    answer = await client.complete(messages)
    return AnswerResult(answer=answer, citations=citations, model=model)
