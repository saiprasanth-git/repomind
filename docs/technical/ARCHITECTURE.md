# RepoMind — System Architecture

## Overview

RepoMind is a codebase-aware AI assistant built on a dual-engine architecture. It ingests GitHub repositories, indexes them using vector embeddings stored in PostgreSQL with pgvector, and answers natural language questions using two different LLM strategies — RAG and long-context prompting.

---

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                       React Frontend                             │
│  (Vite + TypeScript + shadcn/ui + Zustand)                       │
│                                                                  │
│  Pages: RepoInput → IngestionProgress → ChatInterface            │
│  Components: FileExplorer | CodeViewer | DiffPatch | ChatPanel   │
└─────────────────────────┬────────────────────────────────────────┘
                          │ HTTP REST
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                                │
│                                                                  │
│  /api/v1/repos      → Repository management                      │
│  /api/v1/repos/{id}/query  → Question answering                  │
│  /api/v1/repos/{id}/patch  → Patch generation                    │
│  /health            → Liveness + readiness checks                │
└───────────┬──────────────────────────┬───────────────────────────┘
            │                          │
            ▼                          ▼
┌─────────────────────┐    ┌──────────────────────────────────────┐
│  Ingestion Pipeline │    │          Query Engines               │
│                     │    │                                      │
│  1. Clone (GitPython│    │  ┌─────────────────────────────┐    │
│  2. Parse (os.walk) │    │  │  RAG Engine                 │    │
│  3. Chunk (LangChain│    │  │  embed_query() → pgvector   │    │
│  4. Embed (Google)  │    │  │  similarity search → top-K  │    │
│  5. Store (pgvector)│    │  │  chunks → Gemini/GPT-4o     │    │
│  6. Cleanup         │    │  └─────────────────────────────┘    │
└─────────┬───────────┘    │  ┌─────────────────────────────┐    │
          │                │  │  Long-Context Engine        │    │
          ▼                │  │  assemble_full_context()    │    │
┌─────────────────────┐    │  │  → Gemini 1.5 Pro (2M ctx) │    │
│  PostgreSQL + pgvec │    │  └─────────────────────────────┘    │
│                     │    └──────────────────────────────────────┘
│  repositories       │                    │
│  code_chunks        │◄───────────────────┘
│    + HNSW index     │
│  query_logs         │
└─────────────────────┘
```

---

## Data Models

### `repositories`
Tracks every GitHub repo submitted for indexing. One row per repo.

| Column | Type | Purpose |
|---|---|---|
| id | UUID | Primary key |
| github_url | VARCHAR | The original URL |
| owner / name | VARCHAR | Parsed from URL |
| status | ENUM | PENDING → CLONING → INDEXING → READY / FAILED |
| total_chunks | INT | Number of indexed code pieces |
| total_tokens | INT | Estimated token count across all chunks |

### `code_chunks`
The core table. Every indexed piece of code lives here.

| Column | Type | Purpose |
|---|---|---|
| id | UUID | Primary key |
| repository_id | UUID FK | Which repo this belongs to |
| file_path | VARCHAR | Relative path, e.g. `src/auth/login.py` |
| content | TEXT | The actual code text (with file path header) |
| embedding | VECTOR(768) | 768-dimensional embedding for similarity search |
| chunk_index | INT | Position within the file |
| start_line / end_line | INT | Line numbers in original file |
| token_count | INT | Estimated tokens for budget tracking |

**Critical index:** `HNSW` (Hierarchical Navigable Small World) index on the `embedding` column using cosine similarity. Without this index, a similarity search over 100k chunks takes ~200ms. With HNSW, it's ~2ms.

### `query_logs`
Every question asked and answer given, plus performance metrics.
Used by the research experiment to compare RAG vs long-context.

---

## Ingestion Pipeline — Deep Dive

### Phase 1: Clone
```python
git.Repo.clone_from(url, target_dir, depth=1, single_branch=True)
```
- `depth=1` = shallow clone (only latest commit). We don't need history for code understanding. Makes cloning 10-100x faster.
- Clones to `/tmp/repomind_repos/{repo_id}/`
- Deleted after indexing completes

### Phase 2: Parse (`parser.py`)
- Walks the directory tree with `os.walk()`
- Prunes excluded directories in-place (`node_modules`, `.git`, `__pycache__`, etc.) — prevents descending into them at all
- Filters by supported extensions and max file size (500KB)
- Returns `ParsedFile` objects with content, metadata, and SHA-256 content hash
- Content hash used for incremental re-indexing (skip unchanged files)

### Phase 3: Chunk (`chunker.py`)
Uses **LangChain's language-aware recursive character splitters** — not naive character splitting.

For Python files, LangChain splits preferentially at:
1. Class boundaries (`class Foo:`)
2. Function boundaries (`def bar():`)
3. Block boundaries
4. Line boundaries
5. Character boundaries (last resort)

This produces semantically coherent chunks. A function definition and its body stay together.

**Chunk size:** 1,500 characters (~375 tokens) with 200-character overlap.

Every chunk gets the file path prepended:
```
# File: src/auth/login.py
def authenticate_user(username: str, password: str) -> Optional[User]:
    ...
```
This ensures the LLM always knows which file it's reading.

### Phase 4: Embed (`embedder.py`)
Uses Google's `text-embedding-004` model:
- 768-dimensional output vectors
- `task_type="retrieval_document"` for indexing (vs `"retrieval_query"` for search queries)
- Batched in groups of 50 to respect API rate limits
- Runs in thread pool executor to avoid blocking the async event loop

### Phase 5: Store
Batch inserts into `code_chunks` using SQLAlchemy in groups of 200.
PostgreSQL automatically maintains the HNSW index on insert.

### Phase 6: Cleanup
`shutil.rmtree()` removes the local clone. Everything we need is in the database.

---

## Concurrency Model

The ingestion pipeline runs as a `BackgroundTask` in FastAPI:

```
POST /repos
   │
   ├── Validate URL
   ├── Create repository record (status=PENDING)
   ├── Schedule background task: run_ingestion_pipeline(repo_id, url)
   └── Return 202 Accepted immediately
         │
         ▼ (runs asynchronously after response)
   run_ingestion_pipeline()
         │
         ├── Status → CLONING
         ├── Clone repo
         ├── Status → INDEXING
         ├── Parse → Chunk → Embed → Store
         └── Status → READY (or FAILED)
```

The frontend polls `GET /repos/{id}/status` every 2 seconds to show progress.

---

## Embedding Strategy: Why 768 Dimensions?

Google's `text-embedding-004` produces 768-dimensional vectors. This is a sweet spot:
- **Too few dimensions** (e.g. 64): lose semantic nuance — "authentication" and "login" become indistinguishable
- **Too many dimensions** (e.g. 3072): storage bloat (4x more per chunk), negligible quality gain for code
- **768**: ~3KB per chunk embedding, sub-millisecond HNSW search at million-chunk scale

---

## Why HNSW Over IVFFlat?

pgvector supports two index types:
- **IVFFlat**: fast build, slower queries at scale, requires training
- **HNSW**: slower build (~5 min for 1M vectors), faster queries (~2ms), no training required

We chose HNSW because:
1. Build is a one-time cost during ingestion
2. Query latency is more important than index build time
3. No training phase means we can start querying immediately

Parameters: `m=16, ef_construction=64` — standard defaults, good balance of accuracy and speed.

---

## API Design Decisions

### 202 Accepted Pattern
Ingestion returns `202 Accepted` (not `200 OK`) because the work isn't done yet. The client must poll `/status`. This is the correct HTTP semantics for async operations.

### Background Tasks over Celery
For Phase 1, FastAPI's `BackgroundTasks` is sufficient. For production scale, this would be replaced with Celery + Redis to:
- Survive server restarts
- Distribute across multiple workers
- Support retries with exponential backoff

### Cascade Deletes
`Repository` → `CodeChunk` → `QueryLog` cascade on delete. Deleting a repo atomically removes all associated data. No orphan records.

---

## Security Considerations

1. **No user data stored in embeddings** — we only index public repos
2. **GitHub token is optional** — injected via environment variable, never in code
3. **Non-root container** — Dockerfile creates a `repomind` user with UID 1000
4. **Input validation** — Pydantic schemas validate all API inputs before they touch any business logic
5. **SQL injection prevention** — SQLAlchemy ORM with parameterized queries throughout

---

## Phase 2 Preview: Query Engines

The RAG and long-context engines share this interface:

```python
class BaseEngine(ABC):
    @abstractmethod
    async def query(
        self,
        repo_id: UUID,
        question: str,
        db: AsyncSession,
    ) -> QueryResponse:
        ...
```

This allows the API layer to swap engines transparently, and lets the experiment harness call both with identical inputs.
