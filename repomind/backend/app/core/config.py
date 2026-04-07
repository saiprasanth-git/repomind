"""
Core configuration — loads all environment variables and validates them at startup.
Every secret, URL, and tunable parameter lives here. Nothing is hardcoded anywhere else.
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────────────────────
    APP_NAME: str = "RepoMind"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/repomind",
        description="Async PostgreSQL connection string with pgvector extension"
    )
    DATABASE_URL_SYNC: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/repomind",
        description="Sync connection string used only for Alembic migrations"
    )

    # ── LLM Keys ─────────────────────────────────────────────────────────────
    GOOGLE_API_KEY: str = Field(default="", description="Gemini API key from Google AI Studio")
    OPENAI_API_KEY: str = Field(default="", description="OpenAI API key for GPT-4o fallback")

    # ── Model Names ──────────────────────────────────────────────────────────
    GEMINI_MODEL: str = "gemini-1.5-pro"                  # 2M token context window
    GEMINI_FLASH_MODEL: str = "gemini-1.5-flash"          # Faster, cheaper for summaries
    OPENAI_MODEL: str = "gpt-4o"                          # Comparison baseline
    EMBEDDING_MODEL: str = "models/text-embedding-004"    # Google embedding model

    # ── Ingestion Settings ───────────────────────────────────────────────────
    # How we split code files into chunks for the RAG engine
    CHUNK_SIZE: int = 1500        # characters per chunk (~375 tokens)
    CHUNK_OVERLAP: int = 200      # overlap between chunks to preserve context
    MAX_FILE_SIZE_KB: int = 500   # skip files larger than this (binaries, generated code)
    MAX_REPO_SIZE_MB: int = 500   # refuse repos larger than this

    # File extensions we understand and index
    SUPPORTED_EXTENSIONS: list[str] = [
        ".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".go",
        ".rs", ".cpp", ".c", ".h", ".cs", ".rb", ".php",
        ".md", ".txt", ".yaml", ".yml", ".json", ".toml",
        ".sql", ".sh", ".dockerfile", ".tf"
    ]

    # Folders we always skip — they contain noise, not signal
    EXCLUDED_DIRS: list[str] = [
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        "dist", "build", ".next", "coverage", ".pytest_cache",
        "vendor", "target", "bin", "obj"
    ]

    # ── RAG Settings ─────────────────────────────────────────────────────────
    RAG_TOP_K: int = 12           # number of chunks to retrieve per query
    RAG_SIMILARITY_THRESHOLD: float = 0.65  # minimum similarity score to include a chunk

    # ── Long-Context Settings ────────────────────────────────────────────────
    # Gemini 1.5 Pro supports 2,000,000 tokens. We stay well under the limit.
    LONG_CONTEXT_MAX_TOKENS: int = 800_000   # max tokens to send in one request
    LONG_CONTEXT_BUDGET_TOKENS: int = 1_500_000  # warn if repo exceeds this

    # ── GitHub ───────────────────────────────────────────────────────────────
    GITHUB_TOKEN: Optional[str] = Field(default=None, description="Optional: increases rate limits")
    CLONE_BASE_DIR: str = "/tmp/repomind_repos"  # where repos are cloned temporarily

    # ── API ──────────────────────────────────────────────────────────────────
    API_PREFIX: str = "/api/v1"
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """
    Returns a cached singleton of the settings object.
    lru_cache ensures we only parse .env once — not on every request.
    """
    return Settings()


# Module-level convenience alias
settings = get_settings()
