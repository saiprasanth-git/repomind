# How RepoMind Works — Plain English Guide

**Written for:** Non-technical readers, investors, hiring managers, and anyone curious about what this does without wanting to read code.

---

## The Problem We're Solving

Imagine you join a new company. On your first day, your manager hands you a codebase with 500 files, 200,000 lines of code, and says: *"Get familiar with this."*

Where do you start? You'd probably spend days just figuring out where things are — what handles user login, where the payment logic lives, how data flows through the system.

Senior engineers face this constantly when debugging, onboarding teammates, or reviewing code. It's slow, frustrating, and entirely manual today.

**RepoMind solves this.** Paste a GitHub URL, and within minutes you can ask:
- *"Where is the authentication logic?"*
- *"How does the payment flow work?"*
- *"Fix the bug in the order processing module"*
- *"Summarize what this entire codebase does"*

And get back accurate answers with direct links to the exact files and lines of code.

---

## How It Works — Step by Step

### Step 1: You Paste a GitHub URL

You give RepoMind a URL like `https://github.com/stripe/stripe-python`.

### Step 2: We Download the Entire Codebase

RepoMind downloads every file in the repository — Python files, JavaScript files, documentation, configuration — everything. This is like saving a copy of the entire project to our server.

### Step 3: We Read and Cut Every File into Pieces

We read each file and cut it into small, overlapping sections (about 300-400 words each). We overlap them slightly so that context isn't lost at the edges — like making sure a chapter break doesn't cut a sentence in half.

### Step 4: We Create a "Fingerprint" for Each Piece

For each section of code, we use Google's AI to create a numerical "fingerprint" — a list of 768 numbers that captures the *meaning* of that code.

Here's the magic: **similar meanings get similar numbers.** So `"def authenticate_user()"` and `"how does login work?"` will have very similar fingerprints, even though they use completely different words.

These fingerprints are stored in our database.

### Step 5: You Ask a Question

When you type *"where is the login logic?"*, we:
1. Create a fingerprint for your question
2. Search the database for code pieces whose fingerprints are most similar
3. Find the top 12 most relevant pieces of code
4. Send those pieces to Gemini (Google's most powerful AI) along with your question
5. Gemini reads the relevant code and writes a clear answer

### Step 6: You Get an Answer with Sources

Instead of just getting a text answer, you see:
- The explanation in plain English
- The exact files that were used to generate the answer
- The specific lines of code being referenced
- A syntax-highlighted code viewer so you can read the actual code

---

## The Two Approaches We Use (and Why We Compare Them)

RepoMind actually has two different ways of answering questions:

### Approach 1: RAG (Retrieval-Augmented Generation)
*"Find the relevant pages in the book before answering"*

We search for the most relevant code pieces and only send those to the AI. This is fast and cheap, but it relies on our search being accurate. If the right code isn't in the top 12 results, the AI doesn't see it.

### Approach 2: Long-Context (Full Codebase in Context)
*"Read the whole book before answering"*

We send the ENTIRE codebase to Google's Gemini AI at once. Gemini can handle up to 2 million words of context — enough for most codebases. This is slower and more expensive, but the AI sees everything.

### Why Does This Matter?

This is actually a research question that nobody has fully answered: **when should you use each approach?**

RepoMind runs both approaches on a set of 50 real questions across 5 different codebases and measures:
- Which approach gives more accurate answers?
- Which is faster?
- Which costs less?
- For what types of questions does each approach win?

The results are published in our [Research Experiment Report](../technical/EXPERIMENT.md).

---

## The Technology Stack (Simplified)

| Layer | What It Is | Plain English |
|---|---|---|
| React + TypeScript | Frontend framework | Powers the user interface you see in your browser |
| FastAPI (Python) | Backend framework | Handles all the logic behind the scenes |
| PostgreSQL | Database | Stores all the code pieces and their fingerprints |
| pgvector | Database extension | Makes fingerprint similarity search fast |
| Gemini 1.5 Pro | Google AI model | The brain that reads code and writes answers |
| Docker | Containerization | Packages everything so it runs the same anywhere |
| Kubernetes | Container orchestration | Manages multiple copies of the app for reliability |
| Google Cloud Run | Cloud hosting | Where the app lives on the internet |

---

## What Makes This Different

Most AI coding tools (like GitHub Copilot) help you *write* code. RepoMind helps you *understand* code.

The specific technical challenges that make this hard:
1. **Codebases are large** — a typical production codebase has millions of tokens, more than any AI can read at once
2. **Code is interconnected** — a function in one file calls functions in five others; understanding one requires understanding all
3. **Questions require precise answers** — a wrong file reference is worse than no answer
4. **Code changes** — the index needs to stay current with the repository

These are the same problems that companies like [Magic.dev](https://magic.dev) work on at the frontier of AI research. RepoMind is a practical implementation that demonstrates mastery of these challenges.

---

## What You Can Do With It

| Use Case | Example Question |
|---|---|
| Understand a codebase | "Give me a high-level overview of how this application works" |
| Find specific logic | "Where does this app handle payments?" |
| Debug an issue | "Why might users get logged out unexpectedly?" |
| Generate a fix | "Fix the race condition in the order processing code" |
| Onboard to a new repo | "What do I need to know as a new developer on this project?" |
| Code review prep | "What are the most complex parts of this codebase?" |

---

*Built in 48 hours as a portfolio demonstration of AI-native product engineering.*
