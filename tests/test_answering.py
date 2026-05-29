import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import httpx


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from api.answering import (
    OpenAIChatClient,
    build_answer_messages,
    build_citations,
    fallback_answer,
)


class AnsweringTests(unittest.TestCase):
    def test_build_citations_preserves_ranked_source_metadata(self) -> None:
        hits = [
            SimpleNamespace(
                source_path=r"D:\Rag vsf\data\docs\rag_long_whitepaper.pdf",
                chunk_text=(
                    "Section: 3. Embedding Model Migration "
                    "A different dimension model should use a shadow column."
                ),
                section_title="3. Embedding Model Migration",
                page_number=1,
            ),
            SimpleNamespace(
                source_path=r"D:\Rag vsf\data\docs\rag_architecture.md",
                chunk_text="Strategy B keeps vector and graph pipelines separate.",
                section_title="RAG Architecture: Strategy B",
                page_number=None,
            ),
        ]

        citations = build_citations(hits)

        self.assertEqual([citation.id for citation in citations], [1, 2])
        self.assertEqual(citations[0].source_name, "rag_long_whitepaper.pdf")
        self.assertEqual(citations[0].section_title, "3. Embedding Model Migration")
        self.assertEqual(citations[0].page_number, 1)
        self.assertIn("shadow column", citations[0].snippet)
        self.assertEqual(citations[1].source_name, "rag_architecture.md")

    def test_build_answer_messages_include_citations_and_graph_evidence(self) -> None:
        citations = build_citations(
            [
                SimpleNamespace(
                    source_path="data/docs/graphify_intro.md",
                    chunk_text="Graphify edges can include confidence tags such as EXTRACTED.",
                    section_title="Confidence Tags",
                    page_number=1,
                )
            ]
        )
        graph_hits = [
            SimpleNamespace(
                node={"label": "Confidence Tags"},
                relation="MENTIONS",
                confidence="EXTRACTED",
                source_file="graphify_intro.md",
            )
        ]

        messages = build_answer_messages(
            "What confidence tags does graphify use on edges?",
            citations,
            graph_hits,
        )
        content = "\n".join(message["content"] for message in messages)

        self.assertIn("Use only the supplied evidence", content)
        self.assertIn("[1] graphify_intro.md", content)
        self.assertIn("Graph evidence", content)
        self.assertIn("Confidence Tags", content)
        self.assertIn("EXTRACTED", content)

    def test_fallback_answer_is_deterministic_and_cited_requirement_safe(self) -> None:
        answer = fallback_answer("What is missing?")

        self.assertIn("I do not have enough retrieved evidence", answer)
        self.assertIn("What is missing?", answer)

    def test_openai_chat_client_sends_chat_completion_payload(self) -> None:
        seen: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["authorization"] = request.headers.get("authorization")
            seen["json"] = request.read().decode("utf-8")
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "Use a shadow column for new dimensions. [1]",
                            },
                        },
                    ],
                },
            )

        client = OpenAIChatClient(
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
            transport=httpx.MockTransport(handler),
        )

        answer = asyncio.run(
            client.complete(
                [
                    {"role": "system", "content": "Answer with citations."},
                    {"role": "user", "content": "Question"},
                ]
            )
        )

        self.assertEqual(answer, "Use a shadow column for new dimensions. [1]")
        self.assertEqual(seen["url"], "https://api.openai.com/v1/chat/completions")
        self.assertEqual(seen["authorization"], "Bearer test-key")
        self.assertIn('"model":"gpt-4o-mini"', str(seen["json"]))
        self.assertIn('"temperature":0.2', str(seen["json"]))


if __name__ == "__main__":
    unittest.main()
