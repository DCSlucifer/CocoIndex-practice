"""Sample Python code để test AST extraction của graphify."""
from dataclasses import dataclass


@dataclass
class Document:
    doc_id: str
    text: str
    source_path: str


class VectorStore:
    """Lưu embedding vector với pgvector."""

    def __init__(self, conn_string: str):
        self.conn = conn_string

    def upsert(self, doc: Document, embedding: list[float]) -> None:
        pass

    def search(self, query_vec: list[float], top_k: int = 10) -> list[Document]:
        return []


class GraphStore:
    """Wrapper cho graph.json từ graphify."""

    def __init__(self, graph_path: str):
        self.path = graph_path

    def get_neighbors(self, node_id: str, depth: int = 1) -> list[dict]:
        return []


class HybridRetriever:
    """Kết hợp vector search + graph traversal."""

    def __init__(self, vector_store: VectorStore, graph_store: GraphStore):
        self.vs = vector_store
        self.gs = graph_store

    def retrieve(self, query: str, k: int = 5) -> list[Document]:
        return []
