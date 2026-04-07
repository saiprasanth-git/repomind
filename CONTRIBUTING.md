# Contributing to RepoMind

## Local Development Setup

### Prerequisites
- Python 3.12+
- Node.js 20+
- Docker + Docker Compose
- A Google AI Studio API key ([get one free](https://aistudio.google.com/app/apikey))

### 1. Clone and configure

```bash
git clone https://github.com/yourusername/repomind
cd repomind
cp backend/.env.example backend/.env
# Add your API keys to backend/.env
```

### 2. Start the database

```bash
docker compose up postgres -d
# PostgreSQL 16 + pgvector starts on localhost:5432
```

### 3. Start the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# API available at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
# Frontend available at http://localhost:5000
```

## Running Tests

```bash
# Backend tests (no API keys needed)
cd backend && source .venv/bin/activate
pytest tests/ -v

# Run a specific test file
pytest tests/test_engines.py -v

# Run with coverage
pytest tests/ --cov=app --cov-report=term-missing
```

## Running the Experiment

```bash
# Generate simulated results (no API keys needed)
python experiments/scripts/eval_harness.py --simulate

# Generate charts
python experiments/scripts/generate_charts.py

# Run live experiment (requires API keys + indexed repo)
python experiments/scripts/eval_harness.py --live --repo-id <uuid>
```

## Project Structure

```
backend/app/
├── core/config.py        — All settings and env vars
├── db/database.py        — Database setup and session management
├── models/               — SQLAlchemy ORM models
├── schemas/              — Pydantic request/response schemas
├── ingestion/            — Clone → Parse → Chunk → Embed → Store
│   ├── cloner.py         — GitHub clone and metadata
│   ├── parser.py         — File tree walker
│   ├── chunker.py        — Language-aware code splitting
│   ├── embedder.py       — Google embedding API
│   └── pipeline.py       — Full orchestration
├── engines/              — Query engines
│   ├── base.py           — Abstract interface
│   ├── prompts.py        — All LLM prompts
│   ├── rag_engine.py     — Retrieval-augmented generation
│   ├── long_context_engine.py — Full-repo context
│   └── router.py         — Auto-routing logic
└── api/routes/           — HTTP endpoints
    ├── health.py
    ├── repos.py
    └── queries.py
```

## Commit Convention

```
feat: add cross-encoder reranking step to RAG engine
fix: deduplicate overlapping chunks at file boundaries
docs: add interview talking points to PRESENTATION.md
test: add routing boundary condition tests
chore: update requirements.txt to latest versions
```

## Pull Request Process

1. Branch from `main`
2. Make your changes with tests
3. Ensure `pytest tests/ -v` passes
4. Ensure `cd frontend && npm run build` succeeds
5. Open a PR with a clear description of the change

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_API_KEY` | Yes | Google AI Studio key for Gemini + embeddings |
| `OPENAI_API_KEY` | Yes | OpenAI key for GPT-4o comparison |
| `GITHUB_TOKEN` | No | Increases GitHub API rate limit from 60 to 5,000/hr |
| `DATABASE_URL` | Yes | Async PostgreSQL connection string |
