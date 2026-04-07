# RepoMind API Reference

**Base URL:** `https://api.repomind.app/api/v1`  
**Local dev:** `http://localhost:8000/api/v1`  
**Interactive docs:** `http://localhost:8000/docs` (Swagger UI)  
**Auth:** None required (public endpoints)  
**Rate limits:** 60 requests/minute per IP

All requests and responses use JSON. All timestamps are ISO 8601 UTC.

---

## Health

### `GET /health`
Liveness check — is the app running?

**Response 200:**
```json
{
  "status": "healthy",
  "app": "RepoMind",
  "version": "1.0.0",
  "environment": "production"
}
```

### `GET /health/db`
Readiness check — is the database reachable?

**Response 200:**
```json
{ "status": "healthy", "database": "connected" }
```

**Response 503:**
```json
{ "status": "unhealthy", "database": "unreachable" }
```

---

## Repositories

### `GET /repos`
List all indexed repositories.

**Query params:**
| Param | Type | Default | Description |
|---|---|---|---|
| `page` | int | 1 | Page number |
| `page_size` | int | 20 | Results per page (max 100) |

**Response 200:**
```json
{
  "repos": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "github_url": "https://github.com/fastapi/fastapi",
      "owner": "fastapi",
      "name": "fastapi",
      "full_name": "fastapi/fastapi",
      "status": "ready",
      "error_message": null,
      "total_files": 284,
      "indexed_files": 284,
      "total_chunks": 1847,
      "total_tokens": 85420,
      "repo_size_kb": 2048.5,
      "description": "FastAPI framework, high performance, easy to learn",
      "language": "Python",
      "stars": 75000,
      "created_at": "2026-04-07T14:23:00Z",
      "updated_at": "2026-04-07T14:31:00Z",
      "indexed_at": "2026-04-07T14:31:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

---

### `POST /repos`
Start indexing a new repository. Returns immediately (202) — indexing runs in background.

**Request body:**
```json
{ "github_url": "https://github.com/owner/repo" }
```

**Response 202:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "indexed_files": 0,
  "total_files": 0,
  "total_chunks": 0,
  "error_message": null,
  "progress_percent": 0.0
}
```

**Error 409** (already indexed):
```json
{ "detail": "Repository 'fastapi/fastapi' is already indexed. Delete it first to re-index." }
```

**Error 422** (invalid URL):
```json
{ "detail": "Must be a valid GitHub repository URL (e.g. https://github.com/owner/repo)" }
```

---

### `GET /repos/{id}`
Get full details for a repository.

**Response 200:** Full `Repository` object (see above)  
**Response 404:** `{ "detail": "Repository not found" }`

---

### `GET /repos/{id}/status`
Poll ingestion progress. Call every 2 seconds while `status` is `cloning` or `indexing`.

**Response 200:**
```json
{
  "id": "550e8400-...",
  "status": "indexing",
  "indexed_files": 142,
  "total_files": 284,
  "total_chunks": 920,
  "error_message": null,
  "progress_percent": 55.0
}
```

**Status values:**
| Status | Meaning |
|---|---|
| `pending` | Queued, not yet started |
| `cloning` | Downloading from GitHub |
| `indexing` | Parsing, chunking, embedding |
| `ready` | Fully indexed, ready for queries |
| `failed` | Error — see `error_message` |

---

### `GET /repos/{id}/tree`
Get the file tree structure for the explorer sidebar.

**Response 200:**
```json
{
  "tree": {
    "fastapi": {
      "type": "directory",
      "children": {
        "applications.py": {
          "type": "file",
          "language": "Python",
          "extension": ".py",
          "path": "fastapi/applications.py"
        }
      }
    }
  },
  "total_files": 284
}
```

---

### `DELETE /repos/{id}`
Delete a repository and all its indexed chunks. Irreversible.

**Response 204:** No content  
**Response 404:** Not found

---

## Queries

### `POST /repos/{id}/query`
Ask a natural language question about the repository.

**Request body:**
```json
{
  "question": "How does FastAPI handle request validation?",
  "engine": "auto"
}
```

**`engine` options:**
| Value | Behavior |
|---|---|
| `auto` | Smart routing based on repo size and question type (recommended) |
| `rag` | Force RAG — fast, best for targeted questions |
| `long_context` | Force full-codebase context — best for architecture questions |

**Response 200:**
```json
{
  "query_id": "7f3a4b2c-...",
  "question": "How does FastAPI handle request validation?",
  "answer": "FastAPI uses Pydantic for request validation. When you define a path operation function with typed parameters, FastAPI automatically generates a Pydantic model and validates the incoming request data against it...\n\nThe main validation logic lives in `fastapi/dependencies/utils.py` in the `request_params_to_args()` function...",
  "engine_used": "rag",
  "model": "gemini-1.5-pro",
  "sources": [
    {
      "file_path": "fastapi/dependencies/utils.py",
      "start_line": 187,
      "end_line": 241,
      "content_preview": "async def request_params_to_args(\n    required_params: Sequence[ModelField]...",
      "similarity_score": 0.891
    },
    {
      "file_path": "fastapi/routing.py",
      "start_line": 312,
      "end_line": 358,
      "content_preview": "async def app(scope: Scope, receive: Receive, send: Send) -> None:...",
      "similarity_score": 0.847
    }
  ],
  "latency_ms": 423.7,
  "input_tokens": 4218,
  "output_tokens": 387,
  "estimated_cost_usd": 0.00721,
  "created_at": "2026-04-07T15:42:00Z"
}
```

**Notes:**
- `similarity_score` is only present for `rag` engine (0.0 for `long_context`)
- Long-context queries can take 5–45 seconds depending on repo size
- All queries are logged to `query_logs` for analytics and the research experiment

---

### `POST /repos/{id}/patch`
Generate a code patch in unified diff format.

**Request body:**
```json
{
  "description": "Fix the SQL injection vulnerability in the search function",
  "target_file": "fastapi/routing.py"
}
```

**`target_file`** is optional — omit to let the AI find the right file(s).

**Response 200:**
```json
{
  "query_id": "9a2b3c4d-...",
  "description": "Fix the SQL injection vulnerability in the search function",
  "patch": "--- a/fastapi/routing.py\n+++ b/fastapi/routing.py\n@@ -45,7 +45,7 @@\n async def search_users(query: str, db: Session):\n-    result = db.execute(f'SELECT * FROM users WHERE name = \"{query}\"')\n+    result = db.execute('SELECT * FROM users WHERE name = :name', {'name': query})\n     return result.fetchall()",
  "affected_files": ["fastapi/routing.py"],
  "explanation": "The original code concatenated user input directly into the SQL string, allowing SQL injection. The fix uses parameterized queries (SQLAlchemy's `:name` placeholder syntax) which safely escapes all input.",
  "latency_ms": 1847.3,
  "created_at": "2026-04-07T15:43:00Z"
}
```

---

### `GET /repos/{id}/queries`
Get query history for a repository (most recent first).

**Query params:** `limit` (default: 20)

**Response 200:**
```json
{
  "repo_id": "550e8400-...",
  "queries": [
    {
      "id": "7f3a4b2c-...",
      "question": "How does FastAPI handle request validation?",
      "engine": "rag",
      "latency_ms": 423.7,
      "created_at": "2026-04-07T15:42:00Z"
    }
  ]
}
```

---

### `GET /repos/{id}/file-content`
Get full content of a specific file (reconstructed from chunks).

**Query params:** `file_path` (required) — e.g. `?file_path=fastapi/routing.py`

**Response 200:**
```json
{
  "file_path": "fastapi/routing.py",
  "content": "# Copyright 2018 Sebastián Ramírez\n...",
  "language": "Python",
  "extension": ".py",
  "total_lines": 847,
  "chunks": 6
}
```

---

## Error Responses

All errors follow this shape:

```json
{ "detail": "Human-readable error message" }
```

| Status | Meaning |
|---|---|
| 400 | Bad request (e.g. repo not ready yet) |
| 404 | Resource not found |
| 409 | Conflict (e.g. repo already indexed) |
| 422 | Validation error (invalid input) |
| 500 | Internal server error |
| 503 | Service unavailable (database unreachable) |

---

## Rate Limits

| Endpoint | Limit |
|---|---|
| `POST /repos` | 10/hour per IP |
| `POST /repos/{id}/query` | 60/minute per IP |
| `POST /repos/{id}/patch` | 20/minute per IP |
| All other endpoints | 120/minute per IP |

Headers returned on rate limit: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `Retry-After`
