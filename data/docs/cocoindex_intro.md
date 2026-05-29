# Cocoindex Engine Overview

Cocoindex là framework data transformation cho AI, viết core bằng Rust và expose Python SDK.

## Cơ chế Incremental

Cocoindex tracker mỗi row qua fingerprint `hash(source_input) + hash(transform_code)`.
Khi source thay đổi, chỉ những row bị ảnh hưởng được tái xử lý (delta processing).

## Re-index khi đổi embedding model

Khi function `embed_text` đổi (vd swap từ MiniLM sang BGE), hash code đổi
→ engine tự động retire vector cũ và backfill vector mới cho 100% rows.
Không cần script migration thủ công.

## Output targets

Cocoindex hỗ trợ nhiều target: pgvector (Postgres), Qdrant, LanceDB, Neo4j, Kuzu, Kafka.
