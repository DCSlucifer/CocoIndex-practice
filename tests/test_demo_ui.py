import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DemoUiTests(unittest.TestCase):
    def test_demo_html_calls_health_and_answer_endpoints(self) -> None:
        html_path = ROOT / "src" / "api" / "static" / "demo.html"

        html = html_path.read_text(encoding="utf-8")

        self.assertIn("/health", html)
        self.assertIn("/answer", html)
        self.assertIn("How does the system reindex when embedding model changes?", html)
        self.assertIn("Vector Evidence", html)
        self.assertIn("Graph Evidence", html)

    def test_demo_html_supports_evidence_only_query_mode(self) -> None:
        html_path = ROOT / "src" / "api" / "static" / "demo.html"

        html = html_path.read_text(encoding="utf-8")

        # Evidence-only toggle lets the demo hit /query (no LLM cost) as well as /answer.
        self.assertIn('id="evidence-only"', html)
        self.assertIn("Evidence only", html)
        self.assertIn("/query", html)

    def test_demo_html_surfaces_graph_known_and_offline_hint(self) -> None:
        html_path = ROOT / "src" / "api" / "static" / "demo.html"

        html = html_path.read_text(encoding="utf-8")

        # Vector cards surface the graph cross-validation flag.
        self.assertIn("graphBadge", html)
        self.assertIn("graph_known", html)
        # Offline state guides the user to a start command instead of just "offline".
        self.assertIn('id="offline-hint"', html)
        self.assertIn("serve_demo.ps1", html)

    def test_demo_html_guides_safe_manual_embedding_reindex(self) -> None:
        html_path = ROOT / "src" / "api" / "static" / "demo.html"

        html = html_path.read_text(encoding="utf-8")

        self.assertIn("Embedding Model Switch Guide", html)
        self.assertIn("text-embedding-3-large", html)
        self.assertIn("text-embedding-3-small", html)
        self.assertIn("indexing.flow drop", html)
        self.assertIn("indexing.flow update", html)
        self.assertIn("Manual terminal step", html)
        self.assertNotIn("/admin/reindex", html)


if __name__ == "__main__":
    unittest.main()
