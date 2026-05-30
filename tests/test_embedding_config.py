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
    OpenAICocoEmbedder,
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

    def test_changing_model_busts_memo_key_so_reindex_triggers(self) -> None:
        # The reindex trigger: cocoindex re-embeds when the embedder's memo_key
        # changes. Different model/dimension MUST produce a different key, so a
        # model switch invalidates memoized embeddings and forces a rebuild.
        small = EmbeddingConfig(provider="openai", model="text-embedding-3-small", dimensions=1536)
        large = EmbeddingConfig(provider="openai", model="text-embedding-3-large", dimensions=3072)

        self.assertNotEqual(small.memo_key, large.memo_key)
        self.assertNotEqual(small.model_name_for_storage, large.model_name_for_storage)
        self.assertEqual(small.model_name_for_storage, "openai:text-embedding-3-small:1536")
        self.assertEqual(large.model_name_for_storage, "openai:text-embedding-3-large:3072")
        # The cocoindex embedder exposes the same key, so the engine sees the change.
        self.assertEqual(OpenAICocoEmbedder(small).__coco_memo_key__(), small.memo_key)
        self.assertNotEqual(
            OpenAICocoEmbedder(small).__coco_memo_key__(),
            OpenAICocoEmbedder(large).__coco_memo_key__(),
        )

    def test_same_config_keeps_stable_memo_key_so_no_needless_reindex(self) -> None:
        # Identical config must memoize (stable key) so re-running update does
        # not re-embed unchanged rows.
        a = EmbeddingConfig(provider="openai", model="text-embedding-3-small", dimensions=1536)
        b = EmbeddingConfig(provider="openai", model="text-embedding-3-small", dimensions=1536)

        self.assertEqual(a.memo_key, b.memo_key)
        self.assertEqual(a.model_name_for_storage, b.model_name_for_storage)

    def test_same_model_different_dimension_changes_memo_key(self) -> None:
        # Dimension is part of the schema/migration; changing it alone must also
        # trigger a reindex (and a pgvector column migration).
        d1536 = EmbeddingConfig(provider="openai", model="text-embedding-3-large", dimensions=1536)
        d3072 = EmbeddingConfig(provider="openai", model="text-embedding-3-large", dimensions=3072)

        self.assertNotEqual(d1536.memo_key, d3072.memo_key)
        self.assertNotEqual(d1536.model_name_for_storage, d3072.model_name_for_storage)

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
