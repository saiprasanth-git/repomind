"""
Chunker — splits parsed files into smaller, overlapping pieces.

Plain English: Imagine trying to fit a 500-page book into a single text message.
You can't. So instead, we cut the book into 2-page sections, with each section
slightly overlapping the next (so context isn't lost at boundaries).
We do the same for code files. Each section becomes a "chunk" that we can
independently embed and retrieve.

Why overlap? If a function definition starts at the bottom of one chunk
and its body is in the next, without overlap you'd lose the connection.
With overlap, both chunks contain the function signature.
"""
import hashlib
from dataclasses import dataclass

import structlog
from langchain_text_splitters import (
    Language,
    RecursiveCharacterTextSplitter,
)

from app.core.config import settings
from app.ingestion.parser import ParsedFile

logger = structlog.get_logger()


@dataclass
class Chunk:
    """
    A single chunk ready to be embedded and stored.

    file_path:    Which file this came from
    content:      The actual text of this chunk
    chunk_index:  Position within the file (0 = first chunk)
    start_line:   Approximate starting line number in the original file
    end_line:     Approximate ending line number
    content_hash: Hash of content (for deduplication)
    token_count:  Estimated token count
    language:     Programming language
    extension:    File extension
    """
    file_path: str
    content: str
    chunk_index: int
    start_line: int
    end_line: int
    content_hash: str
    token_count: int
    language: str
    extension: str


# Maps our extension strings to LangChain's Language enum
# LangChain uses language-aware splitters that respect code structure
# (e.g., Python splitter splits on class/def boundaries first)
EXTENSION_TO_LANGCHAIN_LANGUAGE: dict[str, Language | None] = {
    ".py":   Language.PYTHON,
    ".ts":   Language.TS,
    ".tsx":  Language.TS,
    ".js":   Language.JS,
    ".jsx":  Language.JS,
    ".java": Language.JAVA,
    ".go":   Language.GO,
    ".rs":   Language.RUST,
    ".cpp":  Language.CPP,
    ".c":    Language.C,
    ".cs":   Language.CSHARP,
    ".rb":   Language.RUBY,
    ".md":   Language.MARKDOWN,
    ".sol":  Language.SOL,
    # For other types, fall back to generic recursive character splitter
}


def _estimate_tokens(text: str) -> int:
    """
    Fast token count estimate without calling the tokenizer.
    Rule of thumb: ~4 characters per token for code (slightly more than prose).
    """
    return len(text) // 4


def _get_splitter(extension: str) -> RecursiveCharacterTextSplitter:
    """
    Returns the most appropriate text splitter for a given file extension.

    Language-aware splitters try to split at natural boundaries:
    - Python: class → function → block boundaries
    - JS/TS: function → block boundaries
    - Generic: paragraph → sentence → character boundaries

    This produces more semantically coherent chunks than just splitting
    every N characters blindly.
    """
    language = EXTENSION_TO_LANGCHAIN_LANGUAGE.get(extension)

    if language:
        return RecursiveCharacterTextSplitter.from_language(
            language=language,
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
        )
    else:
        # Generic splitter for YAML, JSON, SQL, etc.
        return RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            separators=["\n\n", "\n", " ", ""],
        )


def chunk_file(parsed_file: ParsedFile) -> list[Chunk]:
    """
    Splits a ParsedFile into a list of Chunk objects.

    Returns an empty list if the file is too small to need splitting.
    """
    content = parsed_file.content

    # File fits in a single chunk — no need to split
    if len(content) <= settings.CHUNK_SIZE:
        chunk_content = f"# File: {parsed_file.file_path}\n{content}"
        return [
            Chunk(
                file_path=parsed_file.file_path,
                content=chunk_content,
                chunk_index=0,
                start_line=1,
                end_line=parsed_file.line_count,
                content_hash=parsed_file.content_hash,
                token_count=_estimate_tokens(content),
                language=parsed_file.language,
                extension=parsed_file.extension,
            )
        ]

    splitter = _get_splitter(parsed_file.extension)

    try:
        texts = splitter.split_text(content)
    except Exception as e:
        logger.warning(
            "splitter failed, falling back to generic",
            file=parsed_file.file_path,
            error=str(e)
        )
        # Ultimate fallback: naive character splitting
        texts = [
            content[i : i + settings.CHUNK_SIZE]
            for i in range(0, len(content), settings.CHUNK_SIZE - settings.CHUNK_OVERLAP)
        ]

    chunks = []
    cumulative_chars = 0
    lines = content.split("\n")

    for idx, text in enumerate(texts):
        if not text.strip():
            continue

        # Estimate line numbers by character position
        start_char = content.find(text, max(0, cumulative_chars - settings.CHUNK_OVERLAP))
        if start_char == -1:
            start_char = cumulative_chars

        start_line = content[:start_char].count("\n") + 1
        end_line = start_line + text.count("\n")
        cumulative_chars = start_char + len(text)

        chunk_content = f"# File: {parsed_file.file_path}\n{text}"

        # We prepend the file path to every chunk so the LLM always knows
        # which file it's reading, even without additional context.

        chunks.append(
            Chunk(
                file_path=parsed_file.file_path,
                content=chunk_content,
                chunk_index=idx,
                start_line=max(1, start_line),
                end_line=min(end_line, parsed_file.line_count),
                content_hash=hashlib.sha256(chunk_content.encode()).hexdigest(),
                token_count=_estimate_tokens(chunk_content),
                language=parsed_file.language,
                extension=parsed_file.extension,
            )
        )

    logger.debug(
        "file chunked",
        file=parsed_file.file_path,
        chunks=len(chunks),
        total_tokens=sum(c.token_count for c in chunks),
    )

    return chunks
