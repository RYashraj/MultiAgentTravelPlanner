"""
Admin Backend Endpoints.

Provides server-side authorized telemetry & usage data sourced directly
from User, Trip, and AgentRun database models.
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_admin_user
from app.db.models import AgentRun, Trip, User
from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
def get_admin_stats(
    admin: CurrentUser = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Returns system-wide usage metrics and recent agent runs.
    Enforces server-side admin authorization via get_admin_user dependency.
    """
    try:
        total_trips = db.scalar(select(func.count(Trip.id))) or 0
        total_users = db.scalar(select(func.count(User.id))) or 0

        total_agent_runs = db.scalar(select(func.count(AgentRun.id))) or 0
        completed_agent_runs = db.scalar(select(func.count(AgentRun.id)).where(AgentRun.status == "completed")) or 0
        failed_agent_runs = db.scalar(select(func.count(AgentRun.id)).where(AgentRun.status == "failed")) or 0

        # Fetch recent 15 agent runs
        stmt = select(AgentRun).order_by(AgentRun.started_at.desc()).limit(15)
        runs = db.scalars(stmt).all()

        recent_runs_data = []
        for run in runs:
            duration_sec = None
            if run.completed_at and run.started_at:
                duration_sec = round((run.completed_at - run.started_at).total_seconds(), 2)

            recent_runs_data.append({
                "id": str(run.id),
                "trip_id": str(run.trip_id),
                "agent_name": run.agent_name,
                "status": run.status,
                "duration_seconds": duration_sec,
                "started_at": run.started_at.isoformat() if run.started_at else None,
            })

        return {
            "metrics": {
                "total_trips": total_trips,
                "total_users": total_users,
                "total_agent_runs": total_agent_runs,
                "completed_agent_runs": completed_agent_runs,
                "failed_agent_runs": failed_agent_runs,
            },
            "recent_agent_runs": recent_runs_data,
        }
    except Exception as exc:
        logger.exception("Failed to retrieve admin stats")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve system stats",
        )
