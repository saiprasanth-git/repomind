"""
Database setup — creates the async SQLAlchemy engine, session factory,
and a base class that all models inherit from.

We use async PostgreSQL (asyncpg driver) for non-blocking I/O.
pgvector extension gives us a VECTOR column type for storing embeddings.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from app.core.config import settings
import structlog

logger = structlog.get_logger()

# ── Engine ────────────────────────────────────────────────────────────────────
# pool_pre_ping=True: test connections before using them (handles restarts)
# pool_size=10: up to 10 concurrent DB connections
# echo=True in debug mode: prints every SQL query to stdout for debugging
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=settings.DEBUG,
)

# ── Session Factory ───────────────────────────────────────────────────────────
# expire_on_commit=False: keep model attributes accessible after commit
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Base Model ────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """
    All SQLAlchemy ORM models inherit from this.
    Keeps metadata consistent and enables Alembic autogenerate.
    """
    pass


# ── Dependency ────────────────────────────────────────────────────────────────
async def get_db() -> AsyncSession:
    """
    FastAPI dependency that provides a database session per request.
    Automatically commits on success, rolls back on exception, always closes.

    Usage in a route:
        async def my_route(db: AsyncSession = Depends(get_db)):
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Startup Helpers ───────────────────────────────────────────────────────────
async def init_db():
    """
    Called once on app startup.
    1. Creates the pgvector extension if it doesn't exist.
    2. Creates all tables defined in our models.
    """
    async with engine.begin() as conn:
        # pgvector must be installed in PostgreSQL before we can use VECTOR columns
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        logger.info("pgvector extension ready")

        # Import all models so SQLAlchemy knows about them before creating tables
        from app.models import repo, chunk, query_log  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
        logger.info("database tables created")


async def check_db_health() -> bool:
    """Returns True if the database is reachable. Used by the /health endpoint."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("database health check failed", error=str(e))
        return False
