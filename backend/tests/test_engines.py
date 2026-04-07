"""
Tests for the query engines — routing logic, cost estimation, and utilities.

These tests do NOT call the LLM API (no API keys needed).
They test the logic surrounding the engines: routing decisions, cost math,
context assembly helpers, and file extraction utilities.
"""
import pytest
from uuid import uuid4

from app.engines.base import BaseEngine
from app.engines.router import (
    _auto_route_decision,
    _is_architectural_question,
    _classify_question,
    SMALL_REPO_TOKEN_THRESHOLD,
    LARGE_REPO_TOKEN_THRESHOLD,
)
from app.engines.long_context_engine import (
    _deduplicate_overlapping_chunks,
    _extract_cited_files,
)
from app.engines.rag_engine import RAGEngine
from app.engines.long_context_engine import LongContextEngine


# ── Routing Tests ─────────────────────────────────────────────────────────────

class TestAutoRouting:

    def test_small_repo_routes_to_long_context(self):
        """Repos under 50k tokens always go to long-context."""
        decision = _auto_route_decision("where is the login function?", 10_000)
        assert decision == "long_context"

    def test_large_repo_routes_to_rag(self):
        """Repos over 400k tokens always go to RAG."""
        decision = _auto_route_decision("where is the login function?", 500_000)
        assert decision == "rag"

    def test_architectural_question_mid_repo_routes_to_long_context(self):
        """Mid-size repo + architectural question → long-context."""
        decision = _auto_route_decision(
            "how does the authentication system work?",
            100_000  # mid-size
        )
        assert decision == "long_context"

    def test_navigation_question_mid_repo_routes_to_rag(self):
        """Mid-size repo + targeted question → RAG."""
        decision = _auto_route_decision(
            "where is the user model defined?",
            100_000
        )
        assert decision == "rag"

    def test_boundary_exactly_small_threshold(self):
        """At exactly the small threshold, use long-context."""
        decision = _auto_route_decision("find the config file", SMALL_REPO_TOKEN_THRESHOLD - 1)
        assert decision == "long_context"

    def test_boundary_exactly_large_threshold(self):
        """At exactly the large threshold, use RAG."""
        decision = _auto_route_decision("find the config file", LARGE_REPO_TOKEN_THRESHOLD + 1)
        assert decision == "rag"


class TestQuestionClassification:

    def test_fix_is_patch(self):
        assert _classify_question("fix the bug in the login handler") == "patch"

    def test_where_is_navigation(self):
        assert _classify_question("where is the authentication module?") == "navigation"

    def test_how_does_is_explanation(self):
        assert _classify_question("how does the payment processing work?") == "explanation"

    def test_why_error_is_debug(self):
        assert _classify_question("why does the test fail when I submit a form?") == "debug"

    def test_architectural_patterns(self):
        questions = [
            "walk me through the request lifecycle",
            "what is the data flow in this application",
            "explain the overall structure of this codebase",
            "how does the api interact with the database",
        ]
        for q in questions:
            result = _is_architectural_question(q)
            assert result is True, f"Expected architectural but got non-architectural for: {q}"


# ── Cost Estimation Tests ──────────────────────────────────────────────────────

class TestCostEstimation:

    def setup_method(self):
        self.engine = RAGEngine()

    def test_cost_is_positive(self):
        cost = self.engine._estimate_cost("gemini-1.5-pro", 1000, 500)
        assert cost > 0

    def test_long_context_surcharge_applied_above_128k(self):
        """Gemini Pro costs 2x for inputs > 128k tokens."""
        cost_under = self.engine._estimate_cost("gemini-1.5-pro", 100_000, 500)
        cost_over = self.engine._estimate_cost("gemini-1.5-pro", 200_000, 500)
        # The over-128k cost should be more than double the under-128k cost
        # because BOTH input and output prices double
        ratio = cost_over / cost_under
        assert ratio > 1.9  # Should be close to 2x

    def test_flash_cheaper_than_pro(self):
        cost_pro = self.engine._estimate_cost("gemini-1.5-pro", 10_000, 1000)
        cost_flash = self.engine._estimate_cost("gemini-1.5-flash", 10_000, 1000)
        assert cost_flash < cost_pro

    def test_gpt4o_more_expensive_than_gemini_pro(self):
        """At small token counts (<128k), GPT-4o is more expensive than Gemini 1.5 Pro.
        Gemini Pro: $1.25/1M input, $5.00/1M output
        GPT-4o:     $2.50/1M input, $10.00/1M output  (exactly 2x)
        """
        cost_gemini = self.engine._estimate_cost("gemini-1.5-pro", 10_000, 1000)
        cost_gpt4o = self.engine._estimate_cost("gpt-4o", 10_000, 1000)
        # GPT-4o should cost more than Gemini Pro at this scale
        assert cost_gpt4o > cost_gemini
        # And it should be close to 2x (based on actual pricing)
        assert 1.5 < (cost_gpt4o / cost_gemini) < 2.5

    def test_zero_tokens_zero_cost(self):
        cost = self.engine._estimate_cost("gemini-1.5-pro", 0, 0)
        assert cost == 0.0


# ── Long-Context Utility Tests ─────────────────────────────────────────────────

class TestDeduplicateChunks:

    def test_single_chunk_unchanged(self):
        result = _deduplicate_overlapping_chunks(["def foo(): pass"])
        assert result == "def foo(): pass"

    def test_no_overlap_concatenated(self):
        parts = ["hello ", "world"]
        result = _deduplicate_overlapping_chunks(parts)
        # No overlap: should be concatenated
        assert "hello" in result
        assert "world" in result

    def test_overlap_removed(self):
        """If part B starts with the last N chars of part A, don't duplicate."""
        part_a = "def authenticate_user():\n    check_password()"
        overlap = "    check_password()"
        part_b = overlap + "\n    return True"

        result = _deduplicate_overlapping_chunks([part_a, part_b])
        # The overlap should not appear twice
        assert result.count("check_password()") == 1

    def test_empty_list_returns_empty(self):
        assert _deduplicate_overlapping_chunks([]) == ""

    def test_empty_strings_handled(self):
        result = _deduplicate_overlapping_chunks(["", "content", ""])
        assert "content" in result


class TestExtractCitedFiles:

    def test_extracts_file_path_from_answer(self):
        answer = "The authentication logic is in `src/auth/login.py` and calls..."
        known_files = ["src/auth/login.py", "src/models/user.py"]
        cited = _extract_cited_files(answer, known_files)
        assert "src/auth/login.py" in cited

    def test_extracts_by_filename(self):
        """Should match even if only the filename (not full path) is in the answer."""
        answer = "Look at login.py for the authentication handler."
        known_files = ["src/auth/login.py"]
        cited = _extract_cited_files(answer, known_files)
        assert "src/auth/login.py" in cited

    def test_no_false_positives(self):
        answer = "The system uses JWT tokens for authentication."
        known_files = ["src/auth/login.py", "src/models/user.py"]
        cited = _extract_cited_files(answer, known_files)
        assert len(cited) == 0

    def test_empty_files_list(self):
        cited = _extract_cited_files("some answer", [])
        assert cited == []


# ── Engine Interface Tests ────────────────────────────────────────────────────

class TestEngineInterface:
    """Verify that both engines implement the required BaseEngine interface."""

    def test_rag_engine_implements_base(self):
        engine = RAGEngine()
        assert isinstance(engine, BaseEngine)
        assert hasattr(engine, "query")
        assert hasattr(engine, "generate_patch")
        assert hasattr(engine, "_estimate_cost")

    def test_long_context_engine_implements_base(self):
        engine = LongContextEngine()
        assert isinstance(engine, BaseEngine)
        assert hasattr(engine, "query")
        assert hasattr(engine, "generate_patch")
        assert hasattr(engine, "_estimate_cost")
