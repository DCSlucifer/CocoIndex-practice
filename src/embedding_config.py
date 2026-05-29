"""Embedding provider configuration and OpenAI embedding client."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Mapping, Sequence

import httpx
import cocoindex as coco
import numpy as np
import numpy.typing as npt


DEFAULT_OPENAI_EMBED_MODEL = "text-embedding-3-large"
DEFAULT_LOCAL_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
PROJECT_ROOT = Path(__file__).resolve().parents[1]

OPENAI_EMBED_DIMENSIONS = {
    "text-embedding-3-large": 3072,
    "text-embedding-3-small": 1536,
    "text-embedding-ada-002": 1536,
}

LOCAL_EMBED_DIMENSIONS = {
    "sentence-transformers/all-MiniLM-L6-v2": 384,
    "BAAI/bge-large-en-v1.5": 1024,
}

EmbeddingVector = npt.NDArray[np.float32]


@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str
    model: str
    dimensions: int
    api_key: str | None = None
    base_url: str = DEFAULT_OPENAI_BASE_URL
    organization: str | None = None
    project: str | None = None
    timeout_seconds: float = 30.0
    max_retries: int = 3

    @property
    def model_name_for_storage(self) -> str:
        return f"{self.provider}:{self.model}:{self.dimensions}"

    @property
    def memo_key(self) -> tuple[str, str, int, str]:
        return (self.provider, self.model, self.dimensions, self.base_url.rstrip("/"))


def _parse_int(value: str | None, *, name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {value!r}") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be positive, got {parsed}")
    return parsed


def _parse_float(value: str | None, *, name: str, default: float) -> float:
    if value is None or value == "":
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {value!r}") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be positive, got {parsed}")
    return parsed


def _infer_provider(model: str) -> str:
    if model.startswith("text-embedding-"):
        return "openai"
    return "sentence_transformers"


def _default_dimensions(provider: str, model: str) -> int:
    if provider == "openai":
        return OPENAI_EMBED_DIMENSIONS.get(model, 3072)
    return LOCAL_EMBED_DIMENSIONS.get(model, 384)


def embedding_config_from_env(env: Mapping[str, str] | None = None) -> EmbeddingConfig:
    if env is None:
        try:
            from dotenv import load_dotenv

            load_dotenv(PROJECT_ROOT / ".env")
        except ImportError:
            pass
    values = os.environ if env is None else env
    provider_override = values.get("EMBED_PROVIDER")
    provider = provider_override.strip().lower() if provider_override else None
    model = values.get("EMBED_MODEL")
    if model is None or model == "":
        if provider == "sentence_transformers":
            model = DEFAULT_LOCAL_EMBED_MODEL
        else:
            model = DEFAULT_OPENAI_EMBED_MODEL
    if provider is None:
        provider = _infer_provider(model)
    dimensions = _parse_int(values.get("EMBED_DIMENSIONS"), name="EMBED_DIMENSIONS")
    if dimensions is None:
        dimensions = _default_dimensions(provider, model)

    if provider not in {"openai", "sentence_transformers"}:
        raise ValueError(
            "EMBED_PROVIDER must be 'openai' or 'sentence_transformers', "
            f"got {provider!r}",
        )

    return EmbeddingConfig(
        provider=provider,
        model=model,
        dimensions=dimensions,
        api_key=values.get("OPENAI_API_KEY"),
        base_url=values.get("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL),
        organization=values.get("OPENAI_ORG_ID") or values.get("OPENAI_ORGANIZATION"),
        project=values.get("OPENAI_PROJECT_ID") or values.get("OPENAI_PROJECT"),
        timeout_seconds=_parse_float(
            values.get("OPENAI_TIMEOUT_SECONDS"),
            name="OPENAI_TIMEOUT_SECONDS",
            default=30.0,
        ),
        max_retries=_parse_int(values.get("OPENAI_MAX_RETRIES"), name="OPENAI_MAX_RETRIES") or 3,
    )


class OpenAIEmbeddingClient:
    """Small OpenAI embeddings client using httpx to avoid SDK lock-in."""

    def __init__(
        self,
        config: EmbeddingConfig,
        *,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if config.provider != "openai":
            raise ValueError("OpenAIEmbeddingClient requires provider='openai'")
        self._config = config
        self._transport = transport

    def _url(self) -> str:
        return f"{self._config.base_url.rstrip('/')}/embeddings"

    def _headers(self) -> dict[str, str]:
        if not self._config.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required when EMBED_PROVIDER=openai",
            )
        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }
        if self._config.organization:
            headers["OpenAI-Organization"] = self._config.organization
        if self._config.project:
            headers["OpenAI-Project"] = self._config.project
        return headers

    def _payload(self, texts: Sequence[str]) -> bytes:
        payload: dict[str, object] = {
            "model": self._config.model,
            "input": list(texts),
        }
        if self._config.model.startswith("text-embedding-3-") and self._config.dimensions:
            payload["dimensions"] = self._config.dimensions
        return json.dumps(payload, separators=(",", ":")).encode("utf-8")

    def _parse_embeddings(self, response: httpx.Response) -> list[EmbeddingVector]:
        data = response.json()
        embeddings = [
            np.asarray(item["embedding"], dtype=np.float32)
            for item in data.get("data", [])
        ]
        for embedding in embeddings:
            if len(embedding) != self._config.dimensions:
                raise RuntimeError(
                    "OpenAI embedding dimension mismatch: "
                    f"expected {self._config.dimensions}, got {len(embedding)}",
                )
        return embeddings

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout)):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code == 429 or exc.response.status_code >= 500
        return False

    async def embed_many_async(self, texts: Sequence[str]) -> list[EmbeddingVector]:
        if not texts:
            return []
        last_exc: Exception | None = None
        for attempt in range(self._config.max_retries):
            try:
                async with httpx.AsyncClient(
                    transport=self._transport if isinstance(self._transport, httpx.AsyncBaseTransport) else None,
                    timeout=self._config.timeout_seconds,
                ) as client:
                    response = await client.post(
                        self._url(),
                        content=self._payload(texts),
                        headers=self._headers(),
                    )
                response.raise_for_status()
                return self._parse_embeddings(response)
            except Exception as exc:
                last_exc = exc
                if attempt + 1 >= self._config.max_retries or not self._is_retryable(exc):
                    raise
                await asyncio.sleep(0.25 * (2**attempt))
        assert last_exc is not None
        raise last_exc

    async def embed_async(self, text: str) -> EmbeddingVector:
        embeddings = await self.embed_many_async([text])
        if len(embeddings) != 1:
            raise RuntimeError(f"Expected 1 embedding, got {len(embeddings)}")
        return embeddings[0]

    def embed_many_sync(self, texts: Sequence[str]) -> list[EmbeddingVector]:
        if not texts:
            return []
        last_exc: Exception | None = None
        for attempt in range(self._config.max_retries):
            try:
                with httpx.Client(
                    transport=self._transport if isinstance(self._transport, httpx.BaseTransport) else None,
                    timeout=self._config.timeout_seconds,
                ) as client:
                    response = client.post(
                        self._url(),
                        content=self._payload(texts),
                        headers=self._headers(),
                    )
                response.raise_for_status()
                return self._parse_embeddings(response)
            except Exception as exc:
                last_exc = exc
                if attempt + 1 >= self._config.max_retries or not self._is_retryable(exc):
                    raise
                import time

                time.sleep(0.25 * (2**attempt))
        assert last_exc is not None
        raise last_exc

    def embed_sync(self, text: str) -> EmbeddingVector:
        embeddings = self.embed_many_sync([text])
        if len(embeddings) != 1:
            raise RuntimeError(f"Expected 1 embedding, got {len(embeddings)}")
        return embeddings[0]


class OpenAICocoEmbedder:
    """CocoIndex-compatible VectorSchemaProvider for OpenAI embeddings."""

    def __init__(self, config: EmbeddingConfig) -> None:
        if config.provider != "openai":
            raise ValueError("OpenAICocoEmbedder requires provider='openai'")
        self._config = config
        self._client = OpenAIEmbeddingClient(config)

    def __getstate__(self) -> dict[str, object]:
        return {"config": self._config}

    def __setstate__(self, state: dict[str, object]) -> None:
        self._config = state["config"]  # type: ignore[assignment]
        self._client = OpenAIEmbeddingClient(self._config)

    async def __coco_vector_schema__(self):
        from cocoindex.resources import schema as coco_schema

        return coco_schema.VectorSchema(dtype=np.dtype(np.float32), size=self._config.dimensions)

    def __coco_memo_key__(self) -> object:
        return self._config.memo_key

    @coco.fn(memo=True, version=1, logic_tracking="self")
    async def embed(self, text: str) -> EmbeddingVector:
        return await self._client.embed_async(text)


def create_indexing_embedder(config: EmbeddingConfig):
    if config.provider == "openai":
        return OpenAICocoEmbedder(config)
    from cocoindex.ops.sentence_transformers import SentenceTransformerEmbedder

    return SentenceTransformerEmbedder(config.model)
