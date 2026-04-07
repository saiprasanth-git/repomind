# Changelog

All notable changes to RepoMind are documented here.

## [1.0.0] — 2026-04-07 (48-hour build sprint)

### Added

**Phase 1 — Foundation**
- Full monorepo structure with `backend/`, `frontend/`, `experiments/`, `docs/`, `infra/`
- PostgreSQL schema: `repositories`, `code_chunks` (with 768-dim HNSW vector index), `query_logs`
- GitHub ingestion pipeline: clone → parse → language-aware chunk → embed → store → cleanup
- FastAPI backend with async SQLAlchemy + pgvector
- Repository CRUD API (`/repos`, `/repos/{id}`, `/repos/{id}/status`, `/repos/{id}/tree`)
- Docker + docker-compose local dev environment
- 18 backend unit tests (all passing)

**Phase 2 — AI Engines**
- RAG engine: pgvector cosine similarity search → top-K chunks → Gemini/GPT-4o
- Long-Context engine: full codebase assembly → Gemini 1.5 Pro (2M token window)
- Smart query router: auto-selects engine based on repo size + question type
- Patch generation endpoint: unified diff output with plain-English explanation
- Prompt templates: RAG query, long-context query, patch generation, file summary
- Cost estimation model with Gemini 1.5 Pro long-context surcharge above 128k tokens
- 27 additional tests (45 total, all passing)

**Phase 3 — Frontend**
- React + TypeScript + Vite + shadcn/ui + Tailwind CSS
- Custom design system: dark theme, indigo accent, JetBrains Mono code font
- Custom SVG hexagon/circuit logo
- Landing page with GitHub URL input and example repo shortcuts
- Ingestion progress screen with real-time polling and animated step tracker
- 3-panel workspace: file explorer / Monaco code viewer / AI chat
- File explorer with collapsible tree and language-aware color coding
- Monaco Editor code viewer with syntax highlighting and copy button
- Chat panel with engine selector, source citation pills, and cost/latency display
- Zustand store for cross-component UI state
- Typed API client (axios)
- Zero-error, zero-warning production build

**Phase 4 — Research Experiment**
- 50-question evaluation bank across 5 repos (fastapi, langchain, sqlmodel, httpx, pydantic)
- Question types: navigation, explanation, architecture, debug, patch
- Evaluation harness with keyword match, citation recall/precision, latency, cost metrics
- Simulation mode for reproducible demos without API keys
- 6 dark-theme publication-quality charts (matplotlib)
- Full research report (EXPERIMENT.md) — methodology, results, limitations, future work
- Plain-English experiment summary for non-technical readers

**Phase 5 — Polish & Deploy**
- GitHub Actions CI workflow: pytest + TypeScript build on every PR
- GitHub Actions deploy workflow: Docker → GCR → Cloud Run + GCS frontend
- Kubernetes manifests: Deployment, Service, HorizontalPodAutoscaler
- Complete API Reference (all endpoints, request/response schemas, error codes)
- PRESENTATION.md: full interview guide with talking points, Q&A prep, numbers to memorize
- CONTRIBUTING.md: local setup, test instructions, commit conventions
- CHANGELOG.md: this file

### Bug Fixes
- Fixed LangChain 0.3 breaking import change (`langchain.schema` → `langchain_core.messages`)
- Fixed small file chunker not prepending file path header
- Fixed CSS `@import` must precede `@tailwind` directives
- Fixed cost test: Gemini Pro is 2x cheaper than GPT-4o at small token counts (not "similar")

### Architecture Decisions
- **pgvector over Pinecone:** single infrastructure component, JOIN-able with structured data
- **HNSW over IVFFlat:** faster queries at the cost of build time (one-time)
- **202 Accepted pattern:** async ingestion returns immediately, frontend polls
- **Shallow git clone (depth=1):** 10–100x faster, we don't need history
- **Language-aware chunking:** preserves function/class boundaries for better retrieval
- **Chunk overlap 200 chars:** context preservation at boundaries with deduplication on reassembly
