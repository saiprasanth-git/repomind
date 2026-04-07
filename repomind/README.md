# RepoMind 🧠

> Talk to any GitHub repository like it's a senior engineer who knows every file.

[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0-blue)](https://typescriptlang.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791)](https://postgresql.org)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## What Is This?

RepoMind is a codebase-aware AI assistant. Paste any public GitHub URL and ask questions about the code in plain English. Get answers with direct citations to exact files and line numbers.

It also includes a **research experiment** comparing two architectures for code understanding:
- **RAG (Retrieval-Augmented Generation)** — find relevant chunks, answer from those
- **Long-Context** — send the entire repo to Gemini 1.5 Pro (2M token context window)

**→ [Read the non-technical explanation](docs/plain-english/HOW_IT_WORKS.md)**
**→ [Read the architecture deep-dive](docs/technical/ARCHITECTURE.md)**
**→ [Read the research experiment](docs/technical/EXPERIMENT.md)**

---

## Quick Start (Local Development)

### Prerequisites
- Docker + Docker Compose
- Node.js 20+
- A Google AI Studio API key ([get one free](https://aistudio.google.com/app/apikey))

### 1. Clone & configure
```bash
git clone https://github.com/yourusername/repomind
cd repomind

# Copy environment template
cp backend/.env.example backend/.env

# Edit backend/.env and add your API keys
nano backend/.env
```

### 2. Start the backend + database
```bash
docker compose up
```

This starts:
- PostgreSQL 16 with pgvector on port `5432`
- FastAPI backend on port `8000`
- Swagger API docs at `http://localhost:8000/docs`

### 3. Start the frontend
```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`

---

## Project Structure

```
repomind/
├── backend/                    # Python + FastAPI
│   ├── app/
│   │   ├── api/routes/         # HTTP endpoints
│   │   ├── core/               # Config, settings
│   │   ├── db/                 # Database setup
│   │   ├── engines/            # RAG + Long-Context engines  [Phase 2]
│   │   ├── ingestion/          # Clone → Parse → Chunk → Embed → Store
│   │   ├── models/             # SQLAlchemy ORM models
│   │   └── schemas/            # Pydantic request/response types
│   ├── tests/                  # Pytest test suite
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/                   # React + TypeScript + Vite  [Phase 3]
│   └── src/
│       ├── components/         # UI components
│       ├── pages/              # Route-level pages
│       ├── services/           # API client
│       └── stores/             # Zustand state
│
├── experiments/                # Research experiment  [Phase 4]
│   ├── scripts/                # Eval harness
│   ├── data/                   # Test questions + ground truth
│   └── results/                # Metrics, charts, analysis
│
├── docs/
│   ├── plain-english/          # Non-technical documentation
│   └── technical/              # Architecture, API reference, experiment
│
└── docker-compose.yml          # Local development environment
```

---

## API Endpoints (Phase 1)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `GET` | `/health/db` | Database connectivity check |
| `GET` | `/api/v1/repos` | List all indexed repositories |
| `POST` | `/api/v1/repos` | Start indexing a new repo |
| `GET` | `/api/v1/repos/{id}` | Get repo details |
| `GET` | `/api/v1/repos/{id}/status` | Poll ingestion progress |
| `GET` | `/api/v1/repos/{id}/tree` | Get file tree |
| `DELETE` | `/api/v1/repos/{id}` | Delete a repo |

*Query and patch endpoints added in Phase 2.*

---

## Architecture

```
GitHub URL
    │
    ▼
┌─────────────────────────────────────────┐
│          Ingestion Pipeline              │
│  Clone → Parse → Chunk → Embed → Store  │
└───────────────────┬─────────────────────┘
                    │
                    ▼
         PostgreSQL + pgvector
                    │
         ┌──────────┴──────────┐
         │                     │
    RAG Engine          Long-Context Engine
    (retrieval)         (full-repo context)
         │                     │
         └──────────┬──────────┘
                    │
                Gemini 1.5 Pro
                    │
              Answer + Sources
```

---

## Research Experiment

We ran 50 questions across 5 real open-source repositories to answer:

> **When does long-context prompting beat RAG? When does RAG win?**

Key findings:
- RAG wins on **speed** (3-5x faster) and **cost** (8-12x cheaper)
- Long-context wins on **accuracy** for questions requiring cross-file reasoning
- The crossover point is around **~150k tokens** of relevant context
- Question type matters more than repo size

Full methodology and results: [EXPERIMENT.md](docs/technical/EXPERIMENT.md)

---

## Built In

- **48 hours** — solo build sprint
- **Stack:** Python, FastAPI, React, TypeScript, PostgreSQL, pgvector, LangChain, Gemini 1.5 Pro, Docker, GCP Cloud Run

---

## License

MIT — use it, learn from it, build on it.
