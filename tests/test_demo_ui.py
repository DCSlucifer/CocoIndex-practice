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
