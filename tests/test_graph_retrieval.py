import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from api.graph_retrieval import GraphIndex, tokenize_for_graph


class GraphRetrievalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = GraphIndex(ROOT / "data" / "docs" / "graphify-out" / "graph.json")

    def test_tokenizer_normalizes_reindex_terms(self) -> None:
        tokens = tokenize_for_graph("How does re-index change the embedding model?")

        self.assertIn("reindex", tokens)
        self.assertIn("embedding", tokens)
        self.assertIn("model", tokens)

    def test_natural_reindex_question_finds_graph_seeds(self) -> None:
        matches = self.graph.rank_nodes(
            "How does the system reindex when embedding model changes?",
            context_texts=[],
            limit=5,
        )
        labels = {match.node.get("label", "") for match in matches}

        self.assertTrue(any("Re-index" in label or "Embedding Models" in label for label in labels))

    def test_graph_expansion_returns_confidence_metadata(self) -> None:
        hits = self.graph.expand_for_query(
            "VectorStore GraphStore HybridRetriever",
            context_texts=[],
            top_k=6,
            depth=1,
        )

        self.assertGreaterEqual(len(hits), 3)
        self.assertTrue(any(hit.confidence == "EXTRACTED" for hit in hits))
        self.assertTrue(any(hit.relation for hit in hits))

    def test_graph_known_source_filter_excludes_generated_artifacts(self) -> None:
        self.assertTrue(self.graph.is_graph_known_source(r"D:\Rag vsf\data\docs\sample_code.py"))
        self.assertFalse(
            self.graph.is_graph_known_source(
                r"D:\Rag vsf\data\docs\graphify-out\GRAPH_REPORT.md"
            )
        )


if __name__ == "__main__":
    unittest.main()
