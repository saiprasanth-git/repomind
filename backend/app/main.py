"""
RepoMind — FastAPI application entry point.

This file:
1. Creates the FastAPI app instance
2. Registers all routers (URL routes)
3. Sets up CORS (allows the React frontend to call this API)
4. Runs database initialization on startup
5. Configures structured logging

Plain English: This is the "front door" of our backend.
Every HTTP request enters here, gets routed to the right handler,
and the response goes back out.
"""
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.db.database import init_db
from app.api.routes import health, repos, queries
# Configure structured JSON logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer() if settings.DEBUG else structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger()
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs setup code before the app starts accepting requests,
    and cleanup code when it shuts down.
    """
    # ── Startup ──────────────────────────────────────────────────────────────
    logger.info(
        "starting RepoMind",
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
    )
    try:
        await init_db()
        logger.info("database initialized")
    except Exception as e:
        logger.warning("database initialization skipped", error=str(e))
    yield  # App runs here
    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("shutting down RepoMind")
# ── App Instance ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="RepoMind API",
    description=(
        "AI-powered codebase intelligence. "
        "Index any GitHub repository and ask questions about it in plain English."
    ),
    version=settings.APP_VERSION,
    docs_url="/docs",  # Swagger UI — interactive API docs
    redoc_url="/redoc",  # ReDoc — alternative API docs view
    lifespan=lifespan,
)
# ── CORS Middleware ───────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(repos.router, prefix=settings.API_PREFIX)
app.include_router(queries.router, prefix=settings.API_PREFIX)
# ── Root ─────────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "status": "running",
    }
