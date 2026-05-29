import sys
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from indexing.flow import (
    _augment_chunk_text,
    _chunk_hash,
    _file_to_pages,
    _file_to_text,
    _page_number_for_offset,
    _page_starts,
    _section_title_for_offset,
    _split_lang,
    _splitter,
)


class LongPdfIngestionTests(unittest.TestCase):
    def test_long_pdf_extracts_text_and_splits_into_multiple_chunks(self) -> None:
        pdf_path = ROOT / "data" / "docs" / "rag_long_whitepaper.pdf"
        self.assertTrue(pdf_path.exists(), "Run scripts/make_long_pdf.py to create the fixture")

        text = _file_to_text(pdf_path.read_bytes(), ".pdf")
        chunks = _splitter.split(
            text,
            chunk_size=800,
            chunk_overlap=120,
            language=_split_lang(".pdf"),
        )

        self.assertIn("Long-Form Reindexable RAG Architecture", text)
        self.assertIn("Whitepaper", text)
        self.assertIn("Graphify extracts a graph", text)
        self.assertGreaterEqual(len(chunks), 5)
        self.assertTrue(all(chunk.text.strip() for chunk in chunks))

    def test_long_pdf_fixture_does_not_repeat_exact_chunks(self) -> None:
        pdf_path = ROOT / "data" / "docs" / "rag_long_whitepaper.pdf"
        text = _file_to_text(pdf_path.read_bytes(), ".pdf")
        chunks = _splitter.split(
            text,
            chunk_size=800,
            chunk_overlap=120,
            language=_split_lang(".pdf"),
        )
        normalized = [" ".join(chunk.text.casefold().split()) for chunk in chunks]
        duplicates = [count for count in Counter(normalized).values() if count > 1]

        self.assertEqual(duplicates, [])

    def test_section_metadata_and_augmented_chunk_text(self) -> None:
        text = (
            "Document Title\n"
            "1. Problem Statement\nIntro text.\n"
            "2. Scaling Considerations\nProduction needs replicas and cache.\n"
        )

        section = _section_title_for_offset(text, text.index("Production"))
        first_section = _section_title_for_offset(text, 0, text.index("Intro"))
        augmented = _augment_chunk_text("Production needs replicas and cache.", section)

        self.assertEqual(first_section, "1. Problem Statement")
        self.assertEqual(section, "2. Scaling Considerations")
        self.assertTrue(augmented.startswith("Section: 2. Scaling Considerations\n"))
        self.assertEqual(
            _chunk_hash("Repeated text"),
            _chunk_hash("  repeated   text\n"),
        )

    def test_pdf_page_number_is_derived_from_extracted_page_boundaries(self) -> None:
        pdf_path = ROOT / "data" / "docs" / "rag_long_whitepaper.pdf"
        pages = _file_to_pages(pdf_path.read_bytes(), ".pdf")
        starts = _page_starts(pages)
        text = "\n\n".join(pages)
        scaling_offset = text.index("7. Scaling Considerations")

        self.assertEqual(_page_number_for_offset(starts, 0), 1)
        self.assertGreaterEqual(_page_number_for_offset(starts, scaling_offset), 1)


if __name__ == "__main__":
    unittest.main()
