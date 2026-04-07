"""
Chart generator — produces all visualizations for the research report.

Generates 6 publication-quality charts:
  1. Accuracy (keyword match) by engine and question type
  2. Latency distribution: RAG vs Long-Context
  3. Cost per query: RAG vs Long-Context
  4. File citation recall by question type
  5. Accuracy vs cost scatter (the tradeoff chart)
  6. Performance by repo size (token count)
"""

import json
import csv
import math
from pathlib import Path
from collections import defaultdict

# Use only stdlib + matplotlib (no pandas dependency)
import matplotlib
matplotlib.use('Agg')  # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ── Style ─────────────────────────────────────────────────────────────────────
DARK_BG     = "#0D1117"
CARD_BG     = "#161B22"
BORDER      = "#21262D"
INDIGO      = "#7C6DFA"
TEAL        = "#2DD4BF"
AMBER       = "#F59E0B"
ROSE        = "#F87171"
TEXT_PRIMARY   = "#E6EDF3"
TEXT_MUTED     = "#8B949E"

plt.rcParams.update({
    "figure.facecolor":    DARK_BG,
    "axes.facecolor":      CARD_BG,
    "axes.edgecolor":      BORDER,
    "axes.labelcolor":     TEXT_PRIMARY,
    "axes.titlecolor":     TEXT_PRIMARY,
    "xtick.color":         TEXT_MUTED,
    "ytick.color":         TEXT_MUTED,
    "text.color":          TEXT_PRIMARY,
    "grid.color":          BORDER,
    "grid.linestyle":      "--",
    "grid.alpha":          0.5,
    "font.family":         "monospace",
    "font.size":           11,
    "axes.titlesize":      13,
    "axes.titleweight":    "bold",
    "legend.facecolor":    CARD_BG,
    "legend.edgecolor":    BORDER,
    "savefig.facecolor":   DARK_BG,
    "savefig.dpi":         150,
})

RESULTS_PATH = Path(__file__).parent.parent / "results" / "experiment_results.csv"
CHARTS_DIR   = Path(__file__).parent.parent / "results" / "charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)


def load_results() -> list[dict]:
    with open(RESULTS_PATH) as f:
        return list(csv.DictReader(f))


def parse_float(v): return float(v) if v else 0.0
def parse_int(v):   return int(v)   if v else 0


def chart1_accuracy_by_type(rows: list[dict]):
    """Bar chart: keyword match score by engine × question type."""
    qtypes = ["navigation", "explanation", "architecture"]
    engines = ["rag", "long_context"]
    colors = {
        "rag":          INDIGO,
        "long_context": TEAL,
    }
    labels = {"rag": "RAG", "long_context": "Long-Context"}

    scores = defaultdict(lambda: defaultdict(list))
    for r in rows:
        scores[r["engine"]][r["question_type"]].append(parse_float(r["keyword_match_score"]))

    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.arange(len(qtypes))
    width = 0.35
    offsets = [-width/2, width/2]

    for i, engine in enumerate(engines):
        vals = [np.mean(scores[engine].get(qt, [0])) for qt in qtypes]
        bars = ax.bar(x + offsets[i], vals, width, color=colors[engine],
                      label=labels[engine], alpha=0.9, zorder=3)
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                    f"{val:.2f}", ha='center', va='bottom', fontsize=9,
                    color=TEXT_PRIMARY)

    ax.set_xticks(x)
    ax.set_xticklabels([qt.capitalize() for qt in qtypes])
    ax.set_ylabel("Keyword Match Score (0–1)")
    ax.set_title("Answer Quality by Engine and Question Type")
    ax.set_ylim(0, 1.1)
    ax.yaxis.grid(True, zorder=0)
    ax.set_axisbelow(True)
    ax.legend()
    ax.text(0.98, 0.92, "Higher = Better", transform=ax.transAxes,
            fontsize=8, color=TEXT_MUTED, ha='right', va='top')
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "01_accuracy_by_type.png")
    plt.close()
    print("✅ Chart 1: Accuracy by question type")


def chart2_latency_distribution(rows: list[dict]):
    """Box plot: latency distribution for each engine."""
    rag_latencies = [parse_float(r["latency_ms"]) for r in rows if r["engine"] == "rag"]
    lc_latencies  = [parse_float(r["latency_ms"]) for r in rows if r["engine"] == "long_context"]

    fig, axes = plt.subplots(1, 2, figsize=(10, 5))

    # Left: Box plot comparison
    ax = axes[0]
    bp = ax.boxplot([rag_latencies, lc_latencies],
                    labels=["RAG", "Long-Context"],
                    patch_artist=True,
                    medianprops=dict(color=AMBER, linewidth=2),
                    whiskerprops=dict(color=TEXT_MUTED),
                    capprops=dict(color=TEXT_MUTED),
                    flierprops=dict(marker='o', color=TEXT_MUTED, alpha=0.4))

    bp['boxes'][0].set_facecolor(INDIGO + "66")
    bp['boxes'][0].set_edgecolor(INDIGO)
    bp['boxes'][1].set_facecolor(TEAL + "66")
    bp['boxes'][1].set_edgecolor(TEAL)

    ax.set_ylabel("Latency (ms)")
    ax.set_title("Latency Distribution")
    ax.yaxis.grid(True, zorder=0)

    # Annotate medians
    for i, data in enumerate([rag_latencies, lc_latencies], 1):
        med = np.median(data)
        ax.text(i, med + 200, f"{med:.0f}ms", ha='center', fontsize=9,
                color=AMBER, fontweight='bold')

    # Right: Histogram
    ax2 = axes[1]
    bins_rag = np.linspace(min(rag_latencies), max(rag_latencies), 15)
    ax2.hist(rag_latencies, bins=bins_rag, color=INDIGO, alpha=0.7, label="RAG", density=True)

    bins_lc = np.linspace(min(lc_latencies), max(lc_latencies), 15)
    ax2.hist(lc_latencies, bins=bins_lc, color=TEAL, alpha=0.6, label="Long-Context", density=True)

    ax2.set_xlabel("Latency (ms)")
    ax2.set_ylabel("Density")
    ax2.set_title("Latency Distribution (Histogram)")
    ax2.legend()

    # Key stat callout
    speedup = np.mean(lc_latencies) / np.mean(rag_latencies)
    ax2.text(0.97, 0.95, f"LC is {speedup:.0f}× slower\nthan RAG on average",
             transform=ax2.transAxes, fontsize=8, color=TEXT_MUTED,
             ha='right', va='top',
             bbox=dict(boxstyle='round,pad=0.4', facecolor=DARK_BG, edgecolor=BORDER))

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "02_latency_distribution.png")
    plt.close()
    print("✅ Chart 2: Latency distribution")


def chart3_cost_comparison(rows: list[dict]):
    """Cost breakdown by repo (shows where long-context gets expensive)."""
    repos = list(dict.fromkeys(r["repo"] for r in rows))
    repo_short = {r: r.split("/")[-1] for r in repos}

    fig, axes = plt.subplots(1, 2, figsize=(11, 5))

    # Left: Total cost per repo
    ax = axes[0]
    rag_costs = []
    lc_costs  = []
    for repo in repos:
        rag_costs.append(sum(parse_float(r["estimated_cost_usd"]) for r in rows
                             if r["repo"] == repo and r["engine"] == "rag"))
        lc_costs.append(sum(parse_float(r["estimated_cost_usd"]) for r in rows
                            if r["repo"] == repo and r["engine"] == "long_context"))

    x = np.arange(len(repos))
    w = 0.35
    ax.bar(x - w/2, rag_costs, w, label="RAG",          color=INDIGO, alpha=0.9)
    ax.bar(x + w/2, lc_costs,  w, label="Long-Context", color=TEAL,   alpha=0.9)
    ax.set_xticks(x)
    ax.set_xticklabels([repo_short[r] for r in repos], rotation=20, ha='right')
    ax.set_ylabel("Total Cost (USD)")
    ax.set_title("Cost per Repo (10 questions each)")
    ax.legend()
    ax.yaxis.grid(True, zorder=0)
    ax.set_axisbelow(True)

    # Annotate cost ratio
    for i, (rc, lc) in enumerate(zip(rag_costs, lc_costs)):
        ratio = lc / rc if rc > 0 else 0
        ax.text(i + w/2, lc + 0.005, f"{ratio:.0f}×", ha='center',
                fontsize=8, color=TEAL)

    # Right: Token count comparison (log scale)
    ax2 = axes[1]
    rag_tokens = [parse_int(r["input_tokens"]) for r in rows if r["engine"] == "rag"]
    lc_tokens  = [parse_int(r["input_tokens"]) for r in rows if r["engine"] == "long_context"]

    categories = ["RAG\n(avg)", "Long-Context\n(avg)"]
    token_avgs = [np.mean(rag_tokens), np.mean(lc_tokens)]
    colors_bar = [INDIGO, TEAL]

    bars = ax2.bar(categories, token_avgs, color=colors_bar, alpha=0.9, width=0.5)
    ax2.set_ylabel("Avg Input Tokens")
    ax2.set_title("Token Usage Per Query")
    ax2.yaxis.grid(True, zorder=0)
    ax2.set_axisbelow(True)

    for bar, val in zip(bars, token_avgs):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1000,
                 f"{val:,.0f}", ha='center', va='bottom', fontsize=10,
                 color=TEXT_PRIMARY, fontweight='bold')

    ratio = token_avgs[1] / token_avgs[0]
    ax2.text(0.5, 0.9, f"Long-Context uses {ratio:.0f}× more tokens",
             transform=ax2.transAxes, fontsize=9, color=TEXT_MUTED,
             ha='center',
             bbox=dict(boxstyle='round,pad=0.4', facecolor=DARK_BG, edgecolor=BORDER))

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "03_cost_comparison.png")
    plt.close()
    print("✅ Chart 3: Cost comparison")


def chart4_recall_by_type(rows: list[dict]):
    """Grouped bar: file citation recall by question type × engine."""
    qtypes     = ["navigation", "explanation", "architecture"]
    engines    = ["rag", "long_context"]
    colors     = {"rag": INDIGO, "long_context": TEAL}
    labels     = {"rag": "RAG", "long_context": "Long-Context"}

    recalls = defaultdict(lambda: defaultdict(list))
    for r in rows:
        recalls[r["engine"]][r["question_type"]].append(parse_float(r["file_citation_recall"]))

    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.arange(len(qtypes))
    w = 0.35
    offsets = [-w/2, w/2]

    for i, engine in enumerate(engines):
        vals = [np.mean(recalls[engine].get(qt, [0])) for qt in qtypes]
        bars = ax.bar(x + offsets[i], vals, w, color=colors[engine],
                      label=labels[engine], alpha=0.9, zorder=3)
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                    f"{val:.2f}", ha='center', va='bottom', fontsize=9,
                    color=TEXT_PRIMARY)

    ax.set_xticks(x)
    ax.set_xticklabels([qt.capitalize() for qt in qtypes])
    ax.set_ylabel("File Citation Recall (0–1)")
    ax.set_title("File Citation Recall: Does the Engine Find the Right Files?")
    ax.set_ylim(0, 1.15)
    ax.yaxis.grid(True, zorder=0)
    ax.set_axisbelow(True)
    ax.legend()

    # Annotation
    arch_rag = np.mean(recalls["rag"].get("architecture", [0]))
    arch_lc  = np.mean(recalls["long_context"].get("architecture", [0]))
    gain = arch_lc - arch_rag
    ax.annotate(f"+{gain:.2f} recall\nfor architecture",
                xy=(2 + w/2, arch_lc),
                xytext=(2.6, arch_lc + 0.08),
                arrowprops=dict(arrowstyle="->", color=AMBER),
                color=AMBER, fontsize=8)

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "04_recall_by_type.png")
    plt.close()
    print("✅ Chart 4: Citation recall by question type")


def chart5_accuracy_vs_cost(rows: list[dict]):
    """Scatter: accuracy vs cost — the key tradeoff visualization."""
    fig, ax = plt.subplots(figsize=(9, 6))

    for engine, color, label, marker in [
        ("rag",          INDIGO, "RAG",          "o"),
        ("long_context", TEAL,   "Long-Context",  "s"),
    ]:
        data = [(parse_float(r["estimated_cost_usd"]),
                 parse_float(r["keyword_match_score"]),
                 r["question_type"])
                for r in rows if r["engine"] == engine]

        costs   = [d[0] for d in data]
        scores  = [d[1] for d in data]
        qtypes  = [d[2] for d in data]

        ax.scatter(costs, scores, color=color, label=label, marker=marker,
                   alpha=0.65, s=50, zorder=3)

        # Mean point — larger marker
        ax.scatter([np.mean(costs)], [np.mean(scores)], color=color,
                   marker=marker, s=200, zorder=5, edgecolors='white', linewidths=1.5)
        ax.annotate(f"Mean\n${np.mean(costs):.4f}\n{np.mean(scores):.3f}",
                    xy=(np.mean(costs), np.mean(scores)),
                    xytext=(np.mean(costs) + max(costs)*0.05, np.mean(scores) - 0.05),
                    fontsize=8, color=color)

    ax.set_xlabel("Cost per Query (USD)")
    ax.set_ylabel("Keyword Match Score")
    ax.set_title("Accuracy vs Cost — The Core Tradeoff")
    ax.yaxis.grid(True, zorder=0)
    ax.xaxis.grid(True, zorder=0)
    ax.set_axisbelow(True)
    ax.legend()

    # Quadrant labels
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    mid_x = (xlim[0] + xlim[1]) / 2
    mid_y = (ylim[0] + ylim[1]) / 2

    ax.text(xlim[0] + 0.02*(xlim[1]-xlim[0]),
            ylim[1] - 0.05*(ylim[1]-ylim[0]),
            "Best:\nHigh quality, Low cost",
            fontsize=7, color=TEXT_MUTED, alpha=0.7)

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "05_accuracy_vs_cost.png")
    plt.close()
    print("✅ Chart 5: Accuracy vs cost scatter")


def chart6_performance_by_repo_size(rows: list[dict]):
    """Line chart: how each engine's accuracy changes with repo size."""
    # Repo sizes in tokens (from our simulation setup)
    repo_tokens = {
        "tiangolo/sqlmodel":      32_000,
        "encode/httpx":           68_000,
        "fastapi/fastapi":        85_000,
        "pydantic/pydantic":     180_000,
        "langchain-ai/langchain": 420_000,
    }

    repos_sorted = sorted(repo_tokens.keys(), key=lambda r: repo_tokens[r])

    rag_scores = []
    lc_scores  = []
    rag_latencies = []
    lc_latencies  = []

    for repo in repos_sorted:
        rag_q  = [parse_float(r["keyword_match_score"]) for r in rows
                  if r["repo"] == repo and r["engine"] == "rag"]
        lc_q   = [parse_float(r["keyword_match_score"]) for r in rows
                  if r["repo"] == repo and r["engine"] == "long_context"]
        rag_lat = [parse_float(r["latency_ms"]) for r in rows
                   if r["repo"] == repo and r["engine"] == "rag"]
        lc_lat  = [parse_float(r["latency_ms"]) for r in rows
                   if r["repo"] == repo and r["engine"] == "long_context"]

        rag_scores.append(np.mean(rag_q) if rag_q else 0)
        lc_scores.append(np.mean(lc_q) if lc_q else 0)
        rag_latencies.append(np.mean(rag_lat) if rag_lat else 0)
        lc_latencies.append(np.mean(lc_lat) if lc_lat else 0)

    token_counts = [repo_tokens[r] / 1000 for r in repos_sorted]
    repo_names   = [r.split("/")[-1] for r in repos_sorted]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Left: Accuracy vs repo size
    ax = axes[0]
    ax.plot(token_counts, rag_scores, color=INDIGO, marker='o', linewidth=2,
            markersize=7, label="RAG")
    ax.plot(token_counts, lc_scores,  color=TEAL,   marker='s', linewidth=2,
            markersize=7, label="Long-Context")
    ax.set_xlabel("Repo Size (thousands of tokens)")
    ax.set_ylabel("Avg Keyword Match Score")
    ax.set_title("Answer Quality vs Repo Size")
    ax.set_xticks(token_counts)
    ax.set_xticklabels([f"{t:.0f}k\n({n})" for t, n in zip(token_counts, repo_names)],
                       fontsize=8)
    ax.yaxis.grid(True, zorder=0)
    ax.set_axisbelow(True)
    ax.legend()

    # Crossover annotation
    # Find where RAG starts beating LC (or they diverge)
    for i in range(1, len(rag_scores)):
        if lc_scores[i] < lc_scores[i-1] * 0.97:  # LC drops
            ax.axvline(x=token_counts[i], color=AMBER, linestyle='--', alpha=0.6)
            ax.text(token_counts[i] + 5, ax.get_ylim()[0] + 0.02,
                    "LC quality\nstarts degrading", fontsize=7, color=AMBER)
            break

    # Right: Latency vs repo size
    ax2 = axes[1]
    ax2.plot(token_counts, [l/1000 for l in rag_latencies], color=INDIGO,
             marker='o', linewidth=2, markersize=7, label="RAG")
    ax2.plot(token_counts, [l/1000 for l in lc_latencies],  color=TEAL,
             marker='s', linewidth=2, markersize=7, label="Long-Context")
    ax2.set_xlabel("Repo Size (thousands of tokens)")
    ax2.set_ylabel("Avg Latency (seconds)")
    ax2.set_title("Latency vs Repo Size")
    ax2.set_xticks(token_counts)
    ax2.set_xticklabels([f"{t:.0f}k" for t in token_counts], fontsize=9)
    ax2.yaxis.grid(True, zorder=0)
    ax2.set_axisbelow(True)
    ax2.legend()

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "06_performance_by_repo_size.png")
    plt.close()
    print("✅ Chart 6: Performance vs repo size")


if __name__ == "__main__":
    print("Loading experiment results...")
    rows = load_results()
    print(f"Loaded {len(rows)} rows\n")

    chart1_accuracy_by_type(rows)
    chart2_latency_distribution(rows)
    chart3_cost_comparison(rows)
    chart4_recall_by_type(rows)
    chart5_accuracy_vs_cost(rows)
    chart6_performance_by_repo_size(rows)

    print(f"\n✅ All 6 charts saved to experiments/results/charts/")
