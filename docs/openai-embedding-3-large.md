# OpenAI text-embedding-3-large Migration

This codebase now defaults to OpenAI `text-embedding-3-large` for retrieval
quality.

## Active embedding config

- Provider: `openai`
- Model: `text-embedding-3-large`
- Vector dimensions: `3072`
- API key env var: `OPENAI_API_KEY`

The local fallback remains available:

```powershell
$env:EMBED_PROVIDER = "sentence_transformers"
$env:EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
$env:EMBED_DIMENSIONS = "384"
```

## Required reindex

The existing pgvector column was created for 384-dimensional MiniLM vectors.
`text-embedding-3-large` uses 3072 dimensions by default, so existing rows must
be dropped and rebuilt before the API can query the new vectors.

```powershell
$env:OPENAI_API_KEY = "<your key>"
$env:EMBED_PROVIDER = "openai"
$env:EMBED_MODEL = "text-embedding-3-large"
$env:EMBED_DIMENSIONS = "3072"
$env:PYTHONPATH = "src"

.\.venv\Scripts\python.exe -m indexing.flow drop
.\.venv\Scripts\python.exe -m indexing.flow update
```

Start the query API with the same embedding env vars:

```powershell
$env:OPENAI_API_KEY = "<your key>"
$env:EMBED_PROVIDER = "openai"
$env:EMBED_MODEL = "text-embedding-3-large"
$env:EMBED_DIMENSIONS = "3072"
$env:PYTHONPATH = "src"

.\.venv\Scripts\uvicorn.exe api.retrieval:app --host 127.0.0.1 --port 8003
```

Check `/health` before running evaluations. It should report:

```json
{
  "embedding_provider": "openai",
  "embedding_dimensions": 3072
}
```

## Why not GPT-4o mini?

`GPT-4o mini` can generate answers after retrieval, but it is not an embedding
model. Retrieval should use `text-embedding-3-large` or
`text-embedding-3-small`; answer generation can use `gpt-4o-mini`.
