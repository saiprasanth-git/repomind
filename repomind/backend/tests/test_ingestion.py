"""
Tests for the ingestion pipeline — parser, chunker, and cloner utilities.

Run with: pytest tests/ -v
"""
import pytest
from pathlib import Path
import tempfile
import os

from app.ingestion.cloner import parse_github_url
from app.ingestion.parser import ParsedFile, _should_skip_path, _compute_hash
from app.ingestion.chunker import chunk_file, _estimate_tokens


# ── Cloner Tests ──────────────────────────────────────────────────────────────

class TestParseGithubUrl:
    def test_standard_https_url(self):
        owner, repo = parse_github_url("https://github.com/torvalds/linux")
        assert owner == "torvalds"
        assert repo == "linux"

    def test_url_with_trailing_slash(self):
        owner, repo = parse_github_url("https://github.com/openai/openai-python/")
        assert owner == "openai"
        assert repo == "openai-python"

    def test_url_with_git_suffix(self):
        owner, repo = parse_github_url("https://github.com/langchain-ai/langchain.git")
        assert owner == "langchain-ai"
        assert repo == "langchain"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Could not parse GitHub URL"):
            parse_github_url("https://gitlab.com/owner/repo")

    def test_empty_url_raises(self):
        with pytest.raises(ValueError):
            parse_github_url("")

    def test_hyphenated_repo_name(self):
        owner, repo = parse_github_url("https://github.com/google/generative-ai-python")
        assert owner == "google"
        assert repo == "generative-ai-python"


# ── Parser Tests ──────────────────────────────────────────────────────────────

class TestFileParser:
    def setup_method(self):
        """Create a temporary directory with test files for each test."""
        self.test_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up temp directory after each test."""
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_file(self, path: str, content: str) -> Path:
        """Helper to create a file in the test directory."""
        full_path = Path(self.test_dir) / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        return full_path

    def test_skip_node_modules(self):
        file = self._create_file("node_modules/lodash/index.js", "module.exports = {};")
        root = Path(self.test_dir)
        assert _should_skip_path(file, root) is True

    def test_skip_git_directory(self):
        file = self._create_file(".git/config", "[core] repositoryformatversion = 0")
        root = Path(self.test_dir)
        assert _should_skip_path(file, root) is True

    def test_include_python_file(self):
        file = self._create_file("src/main.py", "def main(): pass")
        root = Path(self.test_dir)
        assert _should_skip_path(file, root) is False

    def test_skip_unknown_extension(self):
        file = self._create_file("image.png", "binary")
        root = Path(self.test_dir)
        assert _should_skip_path(file, root) is True

    def test_content_hash_is_deterministic(self):
        content = "def hello_world(): print('hello')"
        hash1 = _compute_hash(content)
        hash2 = _compute_hash(content)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex = 64 chars

    def test_different_content_different_hash(self):
        hash1 = _compute_hash("def foo(): pass")
        hash2 = _compute_hash("def bar(): pass")
        assert hash1 != hash2


# ── Chunker Tests ─────────────────────────────────────────────────────────────

class TestChunker:
    def _make_parsed_file(self, content: str, ext: str = ".py") -> ParsedFile:
        return ParsedFile(
            file_path=f"test/file{ext}",
            content=content,
            extension=ext,
            size_bytes=len(content),
            content_hash=_compute_hash(content),
            language="Python",
            line_count=content.count("\n") + 1,
        )

    def test_small_file_single_chunk(self):
        content = "def hello():\n    return 'world'"
        parsed = self._make_parsed_file(content)
        chunks = chunk_file(parsed)
        assert len(chunks) == 1
        assert chunks[0].chunk_index == 0

    def test_large_file_multiple_chunks(self):
        # Create a file larger than CHUNK_SIZE
        content = "\n".join([f"def function_{i}():\n    return {i}" for i in range(500)])
        parsed = self._make_parsed_file(content)
        chunks = chunk_file(parsed)
        assert len(chunks) > 1

    def test_chunk_contains_file_path(self):
        """Every chunk should have the file path prepended for context."""
        content = "x = 1"
        parsed = self._make_parsed_file(content)
        chunks = chunk_file(parsed)
        assert "test/file.py" in chunks[0].content

    def test_chunk_index_is_sequential(self):
        content = "\n".join([f"def function_{i}():\n    return {i}" for i in range(500)])
        parsed = self._make_parsed_file(content)
        chunks = chunk_file(parsed)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_token_estimate_is_reasonable(self):
        content = "def authenticate(user, password): pass"  # ~40 chars
        assert _estimate_tokens(content) > 0
        assert _estimate_tokens(content) < len(content)  # tokens < chars

    def test_empty_content_returns_single_chunk(self):
        content = "x = 1"
        parsed = self._make_parsed_file(content)
        chunks = chunk_file(parsed)
        assert len(chunks) >= 1
