"""
Health check endpoints.

GET /health  — liveness probe: is the process up and DB reachable?
GET /ready   — readiness probe: are all non-optional dependencies available?
              Never leaks secrets or internal paths.
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)) -> dict:
    """Liveness probe — checks DB connectivity."""
    db_status = "unknown"
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        logger.exception("Database health check failed")
        db_status = "unreachable"

    return {
        "status": "ok",
        "service": "voyagerai-backend",
        "database": db_status,
    }


@router.get("/ready")
def readiness_check(db: Session = Depends(get_db)) -> dict:
    """
    Readiness probe — checks all non-optional service dependencies.
    Reports which optional integrations are configured without leaking values.
    Safe for public exposure (no secrets, no internal paths).
    """
    settings = get_settings()

    # DB check
    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        logger.warning("Readiness: DB check failed")

    # Configured-key checks (boolean only — never value)
    integrations = {
        "gemini": bool(settings.gemini_api_key),
        "openweather": bool(settings.openweather_api_key),
        "google_places": bool(settings.google_places_api_key),
        "amadeus": bool(settings.amadeus_api_key and settings.amadeus_api_secret),
        "supabase_auth": bool(settings.supabase_url and settings.supabase_jwt_secret),
    }

    overall = "ready" if db_ok else "degraded"

    return {
        "status": overall,
        "service": "voyagerai-backend",
        "database": "connected" if db_ok else "unreachable",
        "integrations": integrations,
    }
