# Manual Embedding Model Reindex Commands

Use this sequence when changing embedding model or embedding dimensions.

The UI at `http://127.0.0.1:8003/demo` shows the same command sequence in the **Embedding Model Switch Guide** panel. The UI intentionally does not execute `drop` or `update` because those operations rebuild the live vector index.

## 1. Stop API

In the terminal running Uvicorn, press:

```text
Ctrl+C
```

## 2. Edit `.env`

For OpenAI large:

```env
EMBED_PROVIDER=openai
EMBED_MODEL=text-embedding-3-large
EMBED_DIMENSIONS=3072
```

For OpenAI small:

```env
EMBED_PROVIDER=openai
EMBED_MODEL=text-embedding-3-small
EMBED_DIMENSIONS=1536
```

Keep `OPENAI_API_KEY` unchanged and do not show it on a shared screen.

## 3. Rebuild Vector Index

Run from project root:

```powershell
cd "D:\Rag vsf"
$env:PYTHONPATH="src"
```

Drop the old vector index state:

```powershell
.\.venv\Scripts\python.exe -m indexing.flow drop
```

Build the vector index using the new model:

```powershell
.\.venv\Scripts\python.exe -m indexing.flow update
```

## 4. Restart API

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.retrieval:app --host 127.0.0.1 --port 8003
```

## 5. Confirm Health

Open a second terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8003/health
```

Confirm `model` and `embedding_dimensions` match the selected embedding model.

## Demo Explanation

```text
Changing embedding model is not just changing a UI dropdown.
If dimension changes, the vector DB must be rebuilt.
This POC uses drop/update for a clean rebuild.
Production should use a shadow index/table, verify it, then switch read path without dropping the live index.
```
