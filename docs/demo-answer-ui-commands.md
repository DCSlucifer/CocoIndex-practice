# RAG Answer and UI Demo Commands

Use this after the API is running on port `8003`.

## Open the UI

```text
http://127.0.0.1:8003/demo
```

The UI calls `/answer` and shows:

- final answer from `gpt-4o-mini`;
- citations by source, section, and page;
- vector evidence from pgvector;
- graph evidence from Graphify;
- timing and model metadata.

## Call `/answer` from PowerShell

```powershell
$body = @{
  question = "How does the system reindex when embedding model changes?"
  top_k = 5
  graph_depth = 1
} | ConvertTo-Json
```

```powershell
$a = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8003/answer" -ContentType "application/json" -Body $body
```

Show the final answer:

```powershell
$a.answer
```

Show citations:

```powershell
$a.citations | Select-Object id, source_name, section_title, page_number
```

Show vector evidence:

```powershell
$a.vector_hits | Select-Object source_path, section_title, page_number, rerank_score
```

Show graph evidence:

```powershell
$a.graph_hits | Select-Object confidence, relation, source_file
```

Show models:

```powershell
$a | Select-Object model, retrieval_model, cached
```

## Demo Talking Point

```text
/query is the retrieval/evidence layer.
/answer uses that evidence to generate the final answer with gpt-4o-mini.
Citations come from vector hits because they include source, section, and page.
Graph hits are supporting evidence for relation and confidence context.
```
