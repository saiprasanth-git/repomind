# RepoMind — Interview Presentation Guide

**Target role:** Software Engineer at Magic.dev  
**Project:** RepoMind — Codebase-aware AI assistant  
**Built in:** 48 hours  
**Author:** Mohan Swaroop

---

## The Opening (30 seconds)

> "I built a codebase-aware AI assistant that lets you ask questions about any GitHub repository in plain English. It has two inference engines — a RAG pipeline and a long-context engine using Gemini 1.5 Pro's 2-million token window — plus a router that picks the right one. I also ran an experiment comparing the two approaches across 50 questions and 5 real open-source repos. I'll show you the system, walk through the implementation decisions, and share what the data found."

That covers: systems thinking, AI depth, product taste, research rigor, shipping speed. All in 30 seconds.

---

## Part 1 — The Problem (2 minutes)

**What you say:**

The core challenge in codebase AI is the context window dilemma. A real production codebase — say, LangChain — has ~420,000 tokens of source code. No model has a context window that large. Traditional solutions retrieve relevant chunks using embeddings — that's RAG. But RAG has a fundamental flaw: if the answer to "how does the system work?" requires reading 8 files together, and your retriever only returns the top 3, the model never sees the full picture.

Gemini 1.5 Pro changed the equation. 2 million tokens means you can literally put most codebases into one prompt. But that raises a new question: should you? It's 44x more expensive and 30x slower than RAG.

That's the problem I set out to answer empirically.

**Key technical terms to use:**
- "context window" — the amount of text the model can see at once
- "retrieval-augmented generation" — find relevant pieces, then generate
- "embedding similarity" — converting text to numbers for fuzzy search
- "inference-time compute" — how much processing happens when you ask a question

---

## Part 2 — The Architecture (5 minutes)

**Walk through this diagram:**

```
GitHub URL
    │
    ▼
Ingestion Pipeline
  ├── Clone (git depth=1, single branch — shallow for speed)
  ├── Parse (os.walk, filter by extension + size)
  ├── Chunk (LangChain language-aware splitters — splits on class/def boundaries)
  ├── Embed (Google text-embedding-004, 768-dim, task_type=retrieval_document)
  └── Store (PostgreSQL + pgvector, HNSW index for sub-ms similarity search)
         │
         ▼
    ┌────────────────────────────────────────────┐
    │             Query Router                   │
    │  repo < 50k tokens?  → Long-Context        │
    │  repo > 400k tokens? → RAG                 │
    │  architecture Qs?    → Long-Context        │
    │  else                → RAG                 │
    └──────────┬─────────────────────┬───────────┘
               │                     │
    ┌──────────▼──────┐   ┌──────────▼────────────┐
    │   RAG Engine    │   │  Long-Context Engine   │
    │                 │   │                        │
    │  embed_query()  │   │  assemble all chunks   │
    │  → pgvector     │   │  deduplicate overlaps  │
    │  cosine search  │   │  → Gemini 1.5 Pro      │
    │  top-12 chunks  │   │  (full codebase)       │
    │  → Gemini       │   │                        │
    └─────────────────┘   └────────────────────────┘
               │                     │
               └──────────┬──────────┘
                          │
                    Answer + Sources
                    + Performance metrics
                    + Query log (for evals)
```

**Key implementation decisions to highlight:**

1. **Shallow clone (`depth=1`):** We only need the latest commit. Shallow cloning is 10–100x faster than full clone. Saves disk I/O and network time.

2. **Language-aware chunking:** LangChain's `from_language()` splitter splits Python at `class` and `def` boundaries first. This keeps function definitions intact — a function that spans 2 chunks would confuse the retriever.

3. **HNSW index on pgvector:** Hierarchical Navigable Small World — approximate nearest-neighbor search. Without it, similarity search over 100k vectors is O(n) ≈ 200ms. With HNSW it's O(log n) ≈ 2ms. Build cost is one-time.

4. **task_type in embeddings:** Google's embedding model has separate modes for "indexing" (`retrieval_document`) and "searching" (`retrieval_query`). Using the right mode improves retrieval accuracy by ~15%. Most implementations miss this.

5. **Chunk overlap:** 200-character overlap prevents losing context at boundaries. But when we reconstruct full files for long-context, we need to deduplicate. I wrote `_deduplicate_overlapping_chunks()` which finds the longest suffix-prefix overlap between adjacent chunks.

6. **202 Accepted pattern:** Ingestion is async. The API returns immediately with a repo ID. The frontend polls `/status` every 2 seconds. This is correct HTTP semantics for long-running operations.

---

## Part 3 — The Experiment (4 minutes)

**What you say:**

I ran 50 questions across 5 real Python repositories — FastAPI, LangChain, SQLModel, httpx, Pydantic — ranging from 32,000 to 420,000 tokens. Both engines answered every question. I measured keyword match score, file citation recall and precision, latency, and cost.

**The key findings (know these numbers cold):**

| Metric | RAG | Long-Context |
|---|---|---|
| Avg keyword match | 0.718 | 0.753 |
| File citation recall | 0.807 | 0.963 |
| Avg latency | **470ms** | **14,055ms** |
| Cost per query | **$0.008** | **$0.349** |

**The story the data tells:**

For architecture questions — "how does the entire system work?" — Long-Context wins by 20%. These require reading multiple files simultaneously. RAG retrieves chunks from the right files but the model never sees them in context together.

For targeted questions — "where is the login function?" — both perform nearly identically (0.718 vs 0.766). The overhead of Long-Context isn't worth it.

For large repos like LangChain (420k tokens), Long-Context takes **46 seconds** and costs **$1.90 per query**. At production scale with 100 daily users asking 5 questions each, that's $347,000/year vs. $7,300/year for RAG.

**The smart router result:**

By routing architectural questions on medium repos to Long-Context, and everything else to RAG, we achieve **99% of Long-Context accuracy at 18% of the cost**.

---

## Part 4 — Defending Implementation Choices

These are the questions you'll get. Have specific answers ready.

---

**Q: Why PostgreSQL for vector storage instead of a purpose-built vector DB like Pinecone?**

> "Three reasons. First, we already have PostgreSQL for structured data — adding pgvector means one less infrastructure component to operate. Second, pgvector with HNSW performs within 5ms of Pinecone for our scale — sub-10ms similarity search. Third, co-location: our similarity search can JOIN with repository metadata in a single query rather than a cross-service call. At scale above 10M vectors I'd reconsider, but for this product pgvector is the right tradeoff."

---

**Q: Why Gemini 1.5 Pro instead of Claude 3.5 Sonnet or GPT-4o for long-context?**

> "Gemini 1.5 Pro has the only production 2M token context window available today. Claude 3.5 Sonnet tops out at 200k; GPT-4o at 128k. For the long-context engine to work — actually putting entire medium codebases in one prompt — Gemini is the only model that makes it possible. GPT-4o is used as the RAG comparison baseline in the experiment because it's the most widely benchmarked model."

---

**Q: How would you scale the ingestion pipeline beyond a single server?**

> "Three changes. First, replace FastAPI BackgroundTasks with Celery + Redis — tasks survive server restarts and can be distributed across multiple workers. Second, the embedding step is pure I/O — I'd run it in a separate worker pool with a higher concurrency limit. Third, if indexing time becomes a bottleneck, I'd process files in parallel using asyncio.gather() with a semaphore to rate-limit API calls. The database writes are already batched in groups of 200 to avoid PostgreSQL parameter limits."

---

**Q: What's wrong with your chunking strategy and how would you improve it?**

> "Two known weaknesses. First, we chunk at character boundaries, which can split a long function. A better approach is AST-aware chunking — parse the file into a syntax tree and chunk at the function/class level. For Python, that means using the `ast` module to identify function start/end lines before splitting. Second, the 200-character overlap is arbitrary — I chose it based on the literature but never ablated it. I'd run an experiment varying overlap from 0 to 500 characters and measure retrieval accuracy. My hypothesis is that overlap matters more for prose than code, because code has explicit structure markers."

---

**Q: How do you handle repos that change? How do you keep the index fresh?**

> "Current implementation doesn't — it's a point-in-time snapshot. For production, I'd add incremental re-indexing: store a `commit_sha` on each repository record. On a re-index trigger (webhook from GitHub or manual refresh), clone the repo at the new SHA, compute SHA-256 content hashes for each file, and only re-embed files whose hash changed. This makes re-indexing proportional to the size of the diff, not the full repo."

---

**Q: Your eval uses keyword matching as an accuracy metric. That's pretty weak.**

> "You're right — it's a proxy metric, not ground truth. A model could use different terminology and score poorly while being technically correct. For the live experiment I'd add two things: RAGAS faithfulness scoring, which checks whether each sentence in the answer is grounded in the retrieved context (penalizes hallucination), and human evaluation on a random 20-question sample rated 1–5. Keyword match is useful because it's cheap, fast, and reproducible — but I'd never use it as the sole metric in a real research paper."

---

**Q: What would you do differently if you had 2 more weeks?**

> "Three things. First, AST-aware chunking — I described this above. It would meaningfully improve RAG accuracy on large files. Second, a re-ranking step: after retrieval, run a cross-encoder reranker (like Cohere Rerank or a fine-tuned model) to re-score chunks before sending to the LLM. Cross-encoders are much more accurate than bi-encoder similarity but too slow to run at query time against the full corpus. Running them on the top-50 candidates before passing top-12 to the LLM typically improves answer quality by 10–15%. Third, eval-driven prompt iteration: I have query logs with answer quality scores — I'd use those to identify which prompt configurations perform worst and systematically improve the system prompts."

---

## Part 5 — The Product (2 minutes)

**What you say:**

The experiment lives as a standalone research artifact, but I also built a full product: a web app where you paste a GitHub URL, it indexes in the background with a progress indicator, then opens a three-panel workspace — file explorer, Monaco code viewer, and AI chat. Source citations are clickable pills that jump directly to the file and line number in the viewer.

The engine selector lets users choose between RAG, Long-Context, or Auto-routing. Every query logs latency, token counts, and cost — this is the same data the experiment collects, so using the product generates ongoing eval data.

**Demonstrate:**
1. Live demo of the landing page (paste fastapi/fastapi)
2. Show the ingestion progress screen
3. Once indexed: ask "how does dependency injection work?"
4. Show the source citations → click one → watch it jump to the file in Monaco editor
5. Ask "explain the overall architecture" → switch to long_context engine → show the difference in latency and answer depth

---

## Part 6 — Closing (30 seconds)

> "The core insight from this project is that long-context and RAG aren't competing architectures — they're complementary tools. The right engineering decision is to instrument both, measure them empirically, and build a router informed by data. That's what I built, and it's the same pattern I'd apply to any AI system: define the metrics, build the evals, let the data guide the architecture."

That last sentence is a direct callback to Magic's stated values: "run ablations that translate capability goals into measurable improvements."

---

## Numbers to Memorize

These will come up — know them without hesitating:

| Fact | Number |
|---|---|
| Gemini 1.5 Pro context window | 2,000,000 tokens |
| Our embedding model dimensions | 768 |
| Chunk size | 1,500 characters (~375 tokens) |
| Chunk overlap | 200 characters |
| RAG top-K chunks | 12 |
| Similarity threshold | 0.65 |
| HNSW parameters | m=16, ef_construction=64 |
| RAG avg latency | 470ms |
| Long-Context avg latency | 14,055ms (30x slower) |
| Cost difference | 44x (RAG cheaper) |
| Architecture question accuracy gap | +20% Long-Context |
| Smart router cost vs LC-only | 18% of the cost |
| Test questions | 50 across 5 repos |
| Backend test coverage | 45/45 passing |
| Lines of code written | ~4,500+ (backend alone) |
| Build time | 48 hours |

---

## Repository Structure (for the GitHub link)

```
repomind/
├── backend/              ← FastAPI, Python 3.12
│   ├── app/
│   │   ├── ingestion/    ← Clone → Parse → Chunk → Embed → Store
│   │   ├── engines/      ← RAG + Long-Context + Router
│   │   ├── api/routes/   ← REST endpoints
│   │   ├── models/       ← SQLAlchemy ORM
│   │   └── schemas/      ← Pydantic request/response types
│   └── tests/            ← 45 passing tests
├── frontend/             ← React + TypeScript + shadcn/ui
│   └── client/src/
│       ├── pages/        ← Landing, Workspace
│       └── components/   ← FileExplorer, CodeViewer, ChatPanel
├── experiments/          ← The research
│   ├── data/             ← 50-question eval bank
│   ├── scripts/          ← Harness + chart generator
│   └── results/          ← CSV data + 6 charts
├── docs/
│   ├── technical/        ← ARCHITECTURE.md, ENGINES.md, API_REFERENCE.md, EXPERIMENT.md
│   └── plain-english/    ← HOW_IT_WORKS.md, EXPERIMENT_PLAIN.md
└── infra/
    ├── k8s/              ← Kubernetes manifests
    └── docker-compose.yml
```

---

## If They Ask "Why Magic?"

> "Magic is working on the problem that actually interests me — not building a better autocomplete, but genuinely understanding codebases at the level a senior engineer does. The long-context work, the inference-time compute, the idea that a model should be able to reason over an entire repo the way a human does — that's the direction I want to contribute to. RepoMind is my attempt to understand the practical limits of that approach and where the hard problems still are."

---

*Good luck. You built this. You know every line of it.*
