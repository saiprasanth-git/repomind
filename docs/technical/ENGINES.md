# RepoMind Query Engines — Technical Deep Dive

## Overview

RepoMind has two engines for answering questions about code, and a router that decides which one to use. This document explains how each engine works, why we built them both, and what the tradeoffs are.

---

## Engine 1: RAG (Retrieval-Augmented Generation)

### What It Does
Instead of reading the whole codebase, the RAG engine finds the most relevant pieces of code first — then sends only those pieces to the AI.

### The Flow
```
User question
    │
    ▼
embed_query()                    ← Convert question to a 768-dim vector
    │
    ▼
pgvector similarity search       ← Find top-12 most similar code chunks
    │  (cosine distance, HNSW index, <2ms)
    ▼
Build context string             ← Format chunks with file headers
    │
    ▼
Gemini / GPT-4o                  ← Answer from context only
    │
    ▼
EngineResult + SourceReferences  ← Answer + citation list
```

### The SQL Query
The core of RAG is a single PostgreSQL query using pgvector's `<=>` operator:

```sql
SELECT
    id,
    file_path,
    content,
    start_line,
    end_line,
    1 - (embedding <=> CAST(:query_embedding AS vector)) AS similarity_score
FROM code_chunks
WHERE repository_id = :repo_id
  AND 1 - (embedding <=> CAST(:query_embedding AS vector)) >= 0.65
ORDER BY embedding <=> CAST(:query_embedding AS vector)
LIMIT 12
```

- `<=>` = cosine distance operator (pgvector)
- `1 - distance` = cosine similarity (0.0 to 1.0)
- threshold `0.65` = minimum similarity to include (tunable)
- HNSW index makes this O(log n) instead of O(n)

### Why task_type Matters
We use `task_type="retrieval_document"` when indexing chunks, and `task_type="retrieval_query"` when embedding the question. Google trains these as separate models — using the right task_type improves retrieval accuracy by ~15% compared to using the same embedding for both.

### Strengths
- Fast: 200-500ms total (embedding + retrieval + LLM)
- Cheap: sends ~4,000 tokens vs. 100,000+ for long-context
- Scales to any repo size — doesn't matter if the repo is 10MB or 1GB

### Weaknesses
- Can miss cross-file connections: if understanding the answer requires reading files A and B together, but only A appears in the top-12 results, the answer will be incomplete
- Retrieval quality depends on the embedding model — unusual domain-specific terminology can confuse it

---

## Engine 2: Long-Context

### What It Does
Sends the ENTIRE codebase to Gemini 1.5 Pro at once. No retrieval step — the model sees everything.

### The Flow
```
User question
    │
    ▼
_assemble_full_context()         ← Fetch all chunks, reconstruct files,
    │                               sort alphabetically, build one big string
    ▼
Token budget check               ← If > 800k tokens, truncate with note
    │
    ▼
Gemini 1.5 Pro (2M ctx window)   ← Full codebase + question in one prompt
    │
    ▼
_extract_cited_files()           ← Parse file paths mentioned in answer
    │
    ▼
EngineResult + SourceReferences
```

### Context Assembly
We reconstruct full files from their stored chunks using `_deduplicate_overlapping_chunks()`:

```python
def _deduplicate_overlapping_chunks(parts: list[str]) -> str:
    # For each adjacent pair of chunks:
    # Find the longest suffix of A that is a prefix of B
    # Remove the duplicate overlap
    # This reverses the 200-character overlap we added during chunking
```

Files are assembled in alphabetical order, with clear separators:
```
============================================================
FILE: src/auth/login.py
============================================================
```python
def authenticate_user(username: str, password: str) -> Optional[User]:
    ...
```

This consistent structure helps Gemini navigate the codebase and cite file paths accurately.

### Token Budget
Gemini 1.5 Pro supports 2M tokens, but we cap at 800k for two reasons:
1. Cost: >128k tokens triggers 2x pricing surcharge
2. Latency: larger prompts take longer to process (linear scaling)

If a repo exceeds 800k tokens, we include as many files as possible and append:
```
[NOTE: Repository truncated at token limit. X files not shown.]
```

### Strengths
- No retrieval errors — the model sees the entire codebase
- Excellent for architectural questions requiring cross-file understanding
- No embedding step required — slightly simpler data pipeline

### Weaknesses
- Slow: 3-15 seconds depending on repo size
- Expensive: 8-12x more expensive than RAG for the same question
- Hits limits on very large repos (>800k tokens ≈ ~3M characters of code)

---

## The Router

### Decision Logic
```python
def _auto_route_decision(question: str, total_tokens: int) -> str:
    if total_tokens < 50_000:        # Small repo
        return "long_context"        # Fast and cheap at this size

    if total_tokens > 400_000:       # Very large repo
        return "rag"                 # Long-context would be too slow/expensive

    if _is_architectural_question(question):   # Mid-size + architectural
        return "long_context"        # Needs cross-file understanding

    return "rag"                     # Default for mid-size repos
```

### Why This Routing Matters for the Research Experiment
The router is a hypothesis: we claim that routing improves overall accuracy compared to always using one engine. The experiment validates this by comparing:
- Always RAG
- Always Long-Context
- Smart routing (what RepoMind does)

### Architectural Question Patterns
We detect architectural questions using regex patterns:
```python
ARCHITECTURAL_PATTERNS = [
    r"\bhow does .+ work\b",
    r"\bexplain .+ architecture\b",
    r"\boverall structure\b",
    r"\bdata flow\b",
    r"\bwhat happens when\b",
    r"\bwalk me through\b",
    ...
]
```

---

## Cost Model

| Model | Input (per 1M tokens) | Output (per 1M tokens) | Long-Context Surcharge |
|---|---|---|---|
| Gemini 1.5 Pro | $1.25 | $5.00 | 2x if input > 128k |
| Gemini 1.5 Flash | $0.075 | $0.30 | None |
| GPT-4o | $2.50 | $10.00 | None |

**Practical cost per query:**
- RAG (typical): ~4,000 input tokens = $0.005
- Long-Context (50k token repo): ~52,000 tokens = $0.065
- Long-Context (200k token repo): ~210,000 tokens = $0.53 (surcharge applies)

---

## API Layer

### `POST /api/v1/repos/{id}/query`
```json
{
  "question": "Where is the authentication logic?",
  "engine": "auto"  // "rag", "long_context", or "auto"
}
```

Response:
```json
{
  "query_id": "uuid",
  "question": "Where is the authentication logic?",
  "answer": "The authentication logic is in `src/auth/login.py`...",
  "engine_used": "rag",
  "model": "gemini-1.5-pro",
  "sources": [
    {
      "file_path": "src/auth/login.py",
      "start_line": 42,
      "end_line": 78,
      "content_preview": "def authenticate_user...",
      "similarity_score": 0.891
    }
  ],
  "latency_ms": 312.4,
  "input_tokens": 3847,
  "output_tokens": 412,
  "estimated_cost_usd": 0.00689
}
```

### `POST /api/v1/repos/{id}/patch`
```json
{
  "description": "Fix the SQL injection vulnerability in the search function",
  "target_file": "src/api/search.py"  // optional
}
```

Response includes a unified diff:
```json
{
  "patch": "--- a/src/api/search.py\n+++ b/src/api/search.py\n@@ -45,7 +45,7 @@\n...",
  "affected_files": ["src/api/search.py"],
  "explanation": "The original code concatenated user input directly into the SQL query...",
  "latency_ms": 891.2
}
```

---

## Interview Talking Points

**"Why two engines?"**
> Different query types have different information needs. A question like "where is the login function?" only needs the login file — RAG finds it in 300ms for $0.005. A question like "how does data flow through the entire system?" needs every file — long-context spends $0.50 but sees everything. Building both lets you optimize for quality AND cost simultaneously.

**"What were the hardest implementation decisions?"**
> The chunk deduplication algorithm — we add overlap during ingestion to preserve context at boundaries, but need to reverse it when assembling full files for long-context. The naive approach (just concatenate) produces garbled output. The solution was to find the longest common suffix-prefix between adjacent chunks and remove the duplicate bytes.

**"How would you scale this?"**
> Replace FastAPI BackgroundTasks with Celery + Redis (survive restarts, retry on failure). Shard the pgvector table by repository_id. Add a Redis cache for frequently-asked questions (same question on same repo commit SHA = cached answer). Deploy the embedding step as a separate worker pool since it's I/O-bound, not CPU-bound.
