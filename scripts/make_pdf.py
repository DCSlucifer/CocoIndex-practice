"""Tạo 1 PDF test cho demo."""
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "data" / "docs" / "rag_paper_intro.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(out), pagesize=letter)
    styles = getSampleStyleSheet()
    flow = []

    flow.append(Paragraph("Reindexable RAG with Knowledge Graph", styles["Title"]))
    flow.append(Spacer(1, 14))
    flow.append(Paragraph(
        "We present a RAG architecture that can be re-indexed when the embedding model changes, "
        "using cocoindex's hash-of-code invalidation. Cocoindex tracks each transformation by "
        "fingerprint of its source code; swapping the embed model rewrites the function body, "
        "invalidates the fingerprint, and triggers an automatic backfill.",
        styles["BodyText"]))
    flow.append(Spacer(1, 8))
    flow.append(Paragraph(
        "A complementary knowledge graph is built by graphify using tree-sitter for code AST "
        "extraction and LLM semantic extraction for documents. The graph nodes carry confidence "
        "tags (EXTRACTED, INFERRED, AMBIGUOUS) so the LLM can weigh evidence.",
        styles["BodyText"]))
    flow.append(Spacer(1, 8))
    flow.append(Paragraph(
        "Hybrid retrieval combines vector top-K from pgvector with graph neighbor expansion. "
        "This is shown to improve answer accuracy on entity-centric queries, "
        "and reduces hallucination by exposing structured citations to the LLM.",
        styles["BodyText"]))

    doc.build(flow)
    print(f"Created {out}")


if __name__ == "__main__":
    main()
