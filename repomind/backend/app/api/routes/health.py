"""
Health check endpoint — used by Kubernetes, load balancers, and monitoring.

GET /health → returns 200 if the app is running
GET /health/db → returns 200 if the database is reachable
"""
from fastapi import APIRouter
from app.db.database import check_db_health
from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    """Basic liveness check — is the app running?"""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@router.get("/health/db")
async def health_db():
    """Readiness check — is the database reachable?"""
    db_healthy = await check_db_health()
    status_code = 200 if db_healthy else 503

    return {
        "status": "healthy" if db_healthy else "unhealthy",
        "database": "connected" if db_healthy else "unreachable",
    }
