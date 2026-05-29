# Graphify Knowledge Graph Builder

Graphify chuyển code, docs, PDF, ảnh, video thành knowledge graph có thể query.

## Pipeline

1. **Extract**: tree-sitter AST cho code (33 ngôn ngữ), LLM cho docs/PDF, whisper cho video.
2. **Cluster**: Leiden community detection để tìm god nodes và surprising connections.
3. **Output**: graph.json (query-able), graph.html (visualization), GRAPH_REPORT.md (insights).

## Confidence Tags

Mỗi edge có tag: EXTRACTED (chắc chắn từ AST), INFERRED (LLM suy luận), AMBIGUOUS.
LLM dùng tag này để weight bằng chứng khi trả lời câu hỏi.

## MCP Server

Graphify expose 4 RPC qua MCP: query_graph, get_node, get_neighbors, shortest_path.
LLM agent có thể traverse graph thay vì keyword search.
