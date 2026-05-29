# Graph Report - data\docs  (2026-05-28)

## Corpus Check
- 6 files · ~693 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 41 nodes · 46 edges · 8 communities (7 shown, 1 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]

## God Nodes (most connected - your core abstractions)
1. `VectorStore` - 6 edges
2. `GraphStore` - 5 edges
3. `Document` - 4 edges
4. `str` - 4 edges
5. `HybridRetriever` - 4 edges
6. `Cocoindex Engine Overview` - 4 edges
7. `Graphify Knowledge Graph Builder` - 4 edges
8. `RAG Architecture: Strategy B` - 4 edges
9. `int` - 3 edges
10. `Embedding Models Comparison` - 3 edges

## Surprising Connections (you probably didn't know these)
- None detected - all connections are within the same source files.

## Communities (8 total, 1 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.29
Nodes (5): HybridRetriever, Sample Python code để test AST extraction của graphify., Lưu embedding vector với pgvector., Kết hợp vector search + graph traversal., VectorStore

### Community 1 - "Community 1"
Cohesion: 0.40
Nodes (4): Cocoindex Engine Overview, Cơ chế Incremental, Output targets, Re-index khi đổi embedding model

### Community 2 - "Community 2"
Cohesion: 0.40
Nodes (4): Confidence Tags, Graphify Knowledge Graph Builder, MCP Server, Pipeline

### Community 3 - "Community 3"
Cohesion: 0.40
Nodes (4): Hybrid Retrieval, Pipeline 1: Cocoindex → pgvector, Pipeline 2: Graphify → graph.json, RAG Architecture: Strategy B

### Community 4 - "Community 4"
Cohesion: 0.47
Nodes (3): Document, float, int

### Community 5 - "Community 5"
Cohesion: 0.50
Nodes (3): Bảng so sánh model, Embedding Models Comparison, Khi nào swap model?

### Community 6 - "Community 6"
Cohesion: 0.50
Nodes (3): GraphStore, Wrapper cho graph.json từ graphify., str

## Knowledge Gaps
- **12 isolated node(s):** `Cơ chế Incremental`, `Re-index khi đổi embedding model`, `Output targets`, `Nội dung kiểm tra`, `Bảng so sánh model` (+7 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `VectorStore` connect `Community 0` to `Community 4`?**
  _High betweenness centrality (0.057) - this node is a cross-community bridge._
- **Why does `GraphStore` connect `Community 6` to `Community 0`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Why does `HybridRetriever` connect `Community 0` to `Community 4`?**
  _High betweenness centrality (0.029) - this node is a cross-community bridge._
- **What connects `Sample Python code để test AST extraction của graphify.`, `Lưu embedding vector với pgvector.`, `Wrapper cho graph.json từ graphify.` to the rest of the system?**
  _16 weakly-connected nodes found - possible documentation gaps or missing edges._