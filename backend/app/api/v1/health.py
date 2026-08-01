"""
Health check endpoint.

This is the Week 2 "does everything actually connect" proof:
- API is up
- DB connection works (runs a real SELECT 1, not just "did the app boot")
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)) -> dict:
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
