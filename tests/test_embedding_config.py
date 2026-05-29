import asyncio
import sys
import unittest
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from embedding_config import (
    DEFAULT_OPENAI_EMBED_MODEL,
    EmbeddingConfig,
    OpenAIEmbeddingClient,
    embedding_config_from_env,
)


class EmbeddingConfigTests(unittest.TestCase):
    def test_default_embedding_config_uses_openai_large_3072(self) -> None:
        config = embedding_config_from_env({})

        self.assertEqual(config.provider, "openai")
        self.assertEqual(config.model, DEFAULT_OPENAI_EMBED_MODEL)
        self.assertEqual(config.dimensions, 3072)

    def test_local_sentence_transformer_config_keeps_384_dimensions(self) -> None:
        config = embedding_config_from_env(
            {
                "EMBED_PROVIDER": "sentence_transformers",
                "EMBED_MODEL": "sentence-transformers/all-MiniLM-L6-v2",
            },
        )

        self.assertEqual(config.provider, "sentence_transformers")
        self.assertEqual(config.model, "sentence-transformers/all-MiniLM-L6-v2")
        self.assertEqual(config.dimensions, 384)

    def test_local_provider_without_model_uses_local_default(self) -> None:
        config = embedding_config_from_env({"EMBED_PROVIDER": "sentence_transformers"})

        self.assertEqual(config.provider, "sentence_transformers")
        self.assertEqual(config.model, "sentence-transformers/all-MiniLM-L6-v2")
        self.assertEqual(config.dimensions, 384)

    def test_openai_client_sends_embedding_payload(self) -> None:
        seen: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["authorization"] = request.headers.get("authorization")
            seen["json"] = request.read().decode("utf-8")
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "embedding": [0.1, 0.2, 0.3],
                        },
                    ],
                },
            )

        config = EmbeddingConfig(
            provider="openai",
            model="text-embedding-3-large",
            dimensions=3,
            api_key="test-key",
        )
        client = OpenAIEmbeddingClient(config, transport=httpx.MockTransport(handler))

        embedding = asyncio.run(client.embed_async("hello"))

        self.assertEqual(len(embedding), 3)
        self.assertAlmostEqual(float(embedding[0]), 0.1)
        self.assertAlmostEqual(float(embedding[1]), 0.2)
        self.assertAlmostEqual(float(embedding[2]), 0.3)
        self.assertEqual(seen["url"], "https://api.openai.com/v1/embeddings")
        self.assertEqual(seen["authorization"], "Bearer test-key")
        self.assertIn('"model":"text-embedding-3-large"', str(seen["json"]))
        self.assertIn('"dimensions":3', str(seen["json"]))


if __name__ == "__main__":
    unittest.main()
