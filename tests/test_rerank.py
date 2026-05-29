import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from api.rerank import RetrievalCandidate, dedupe_candidates, rule_rerank


class RerankTests(unittest.TestCase):
    def test_dedupe_candidates_keeps_highest_scoring_hash(self) -> None:
        candidates = [
            RetrievalCandidate(
                source_path="doc.pdf",
                text="same text",
                vector_score=0.4,
                chunk_hash="same",
            ),
            RetrievalCandidate(
                source_path="doc.pdf",
                text="same text",
                vector_score=0.6,
                chunk_hash="same",
            ),
            RetrievalCandidate(
                source_path="other.pdf",
                text="different text",
                vector_score=0.5,
                chunk_hash="different",
            ),
        ]

        deduped = dedupe_candidates(candidates)

        self.assertEqual([item.chunk_hash for item in deduped], ["same", "different"])
        self.assertEqual(deduped[0].vector_score, 0.6)

    def test_rule_rerank_promotes_section_title_match_over_intro(self) -> None:
        candidates = [
            RetrievalCandidate(
                source_path="whitepaper.pdf",
                text="Problem Statement production RAG system source metadata evidence",
                vector_score=0.504,
                chunk_hash="intro",
                section_title="1. Problem Statement",
            ),
            RetrievalCandidate(
                source_path="whitepaper.pdf",
                text="The local single-process API is useful for a POC but insufficient for high CCU.",
                vector_score=0.490,
                chunk_hash="scaling",
                section_title="7. Scaling Considerations",
            ),
        ]

        reranked = rule_rerank(
            "What scaling considerations are described in the long-form RAG whitepaper?",
            candidates,
        )

        self.assertEqual(reranked[0].chunk_hash, "scaling")
        self.assertGreater(reranked[0].rerank_score, reranked[1].rerank_score)


if __name__ == "__main__":
    unittest.main()
