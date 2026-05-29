import sys
import unittest
from pathlib import PurePath, Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from indexing.flow import build_path_matcher
from drift_test import format_result_lines


class OperationsTests(unittest.TestCase):
    def test_cocoindex_path_matcher_excludes_graphify_output(self) -> None:
        matcher = build_path_matcher()

        self.assertTrue(matcher.is_file_included(PurePath("sample_code.py")))
        self.assertTrue(matcher.is_file_included(PurePath("rag_paper_intro.pdf")))
        self.assertFalse(matcher.is_file_included(PurePath("graphify-out/GRAPH_REPORT.md")))
        self.assertFalse(matcher.is_file_included(PurePath("graphify-out/cache/ast/a.json")))

    def test_drift_result_lines_are_windows_console_safe(self) -> None:
        text = "\n".join(format_result_lines(dt_cocoindex=1.33, dt_graphify=0.91))

        text.encode("cp1258")
        self.assertIn("Drift window", text)
        self.assertIn("worst-case batch mode", text)


if __name__ == "__main__":
    unittest.main()
