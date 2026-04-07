# The Experiment — Plain English Version

**What we tested:** Two different ways of using AI to answer questions about code.  
**Why it matters:** The answer changes how we build AI coding tools — and could save companies millions in API costs.

---

## The Question We Were Trying to Answer

When you ask an AI "how does this codebase work?", there are two very different approaches:

### Approach A: Find, Then Answer (RAG)
Search the codebase for the most relevant pieces, then show only those pieces to the AI.

It's like asking a librarian to find the right chapters before you read them.

**Pro:** Fast (under 1 second), cheap (less than 1 cent)  
**Con:** If the librarian picks the wrong chapters, the AI misses important context

### Approach B: Read Everything, Then Answer (Long-Context)
Give the AI the ENTIRE codebase at once. Google's Gemini can hold up to 2 million words in memory simultaneously — enough for most real codebases.

It's like a developer who has memorized every file before answering your question.

**Pro:** Sees everything — can't miss connections between distant files  
**Con:** Slow (10–45 seconds), expensive ($0.50–$2.00 per question)

---

## What We Tested

We wrote 50 questions about 5 real, popular open-source coding projects and asked both approaches to answer every single one. We measured:

- Were the answers correct?
- Did they point to the right files?
- How long did each answer take?
- How much did each answer cost?

---

## What We Found

### Finding 1: For simple questions, both approaches work equally well

Questions like "where is the login function defined?" or "show me where file uploads are handled" — both approaches answered these correctly about 73% of the time. The difference was negligible.

**Real-world meaning:** For day-to-day coding questions, the cheaper/faster approach is just as good.

---

### Finding 2: For complex architectural questions, reading everything wins — by a lot

Questions like "explain how the entire request lifecycle works" or "what is the data flow from user to database?" — these require reading 5–8 different files and understanding how they connect.

| Question Type | Quick Search (RAG) | Read Everything (LC) | Difference |
|---|---|---|---|
| "Where is X?" | 72% | 77% | Small |
| "How does X work?" | 76% | 76% | Negligible |
| "Explain the architecture" | **61%** | **73%** | **+20% — significant** |

**Real-world meaning:** When a developer is trying to understand a large, complex system they've never seen before, the "read everything" approach gives meaningfully better answers.

---

### Finding 3: The "read everything" approach gets brutally expensive for large projects

| Project Size | Read Everything Cost | Quick Search Cost | Difference |
|---|---|---|---|
| Small (32k words) | $0.06/question | $0.008/question | 7x |
| Medium (85k words) | $0.14/question | $0.008/question | 17x |
| Large (180k words) | $0.60/question | $0.008/question | 75x |
| Very large (420k words) | $1.90/question | $0.009/question | **211x** |

For the largest project we tested (LangChain, a popular AI library), "read everything" costs **$1.90 per question** and takes **46 seconds to answer**. At a company with 100 developers asking 5 questions a day each, that's $3,800/day — or **$1.4 million per year** — versus $18/day for Quick Search.

---

### Finding 4: A "smart router" gets you most of the accuracy at a fraction of the cost

Instead of always using one approach, we built a system that decides which approach to use based on:
1. How big is the codebase?
2. What kind of question is being asked?

**The smart router's rules:**
- Small project? → Read everything (fast and cheap at this size anyway)
- Big project + architectural question? → Read everything (worth the cost)
- Big project + specific question? → Quick Search (just as accurate, 50x cheaper)

**Results:**

| Strategy | Accuracy | Cost per question |
|---|---|---|
| Always Quick Search | 72% | $0.008 |
| Always Read Everything | 75% | $0.35 |
| **Smart Router** | **74%** | **$0.06** |

The Smart Router achieves **99% of the accuracy** of "read everything" at just **17% of the cost**.

---

## Why This Matters Beyond Our Project

This is the same tradeoff that every AI company building code assistants faces — GitHub Copilot, Cursor, Magic.dev, and dozens of others. The conventional wisdom used to be "retrieval is always the answer." 

Our experiment shows it's more nuanced:

1. **Short context = retrieval wins.** Models with 32k context windows have no choice but to retrieve.
2. **Long context changes the game.** When a model can hold 2 million tokens, "read everything" becomes viable for most real codebases.
3. **But cost makes routing essential.** You can't just always use long-context in a production product — the economics don't work.
4. **The question type is the key signal.** Not repo size — question type. "How does X work globally?" → long-context. "Where is function Y?" → retrieval.

---

## The Bottom Line

> "Use retrieval for precision, long-context for architecture — and build a router smart enough to know the difference."

---

*This experiment was built and run as part of RepoMind, a codebase-aware AI assistant project.*  
*All code, data, and charts are in the `experiments/` folder of the repository.*
