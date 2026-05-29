# Embedding Models Comparison

## Bảng so sánh model

| Model | Dimensions | Cost | Use case |
|-------|-----------|------|----------|
| all-MiniLM-L6-v2 | 384 | Free local | Demo, prototype |
| BGE-large-en-v1.5 | 1024 | Free local (lớn) | Production quality |
| text-embedding-3-small | 1536 | $0.02/1M tokens | Cloud, balanced |
| text-embedding-3-large | 3072 | $0.13/1M tokens | Cloud, best quality |

Current best-quality default: `text-embedding-3-large` with 3072 dimensions.

## Khi nào swap model?

- Accuracy thấp ở recall benchmark: thử model lớn hơn.
- Latency cao: chọn dim nhỏ hơn (MiniLM 384d).
- Budget vượt: chuyển từ OpenAI sang local.

Cocoindex giúp swap không đau: chỉ cần sửa function embed_text → reindex tự động.
