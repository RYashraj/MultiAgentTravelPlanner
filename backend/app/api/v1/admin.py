import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.db.models import User, Trip, AgentRun
from app.core.exceptions import VoyagerError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/stats")
def get_admin_stats(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Returns basic usage stats.
    For this MVP, any authenticated user can view the dashboard.
    In a real app, we would verify `user.is_admin` here.
    """
    try:
        total_users = db.query(User).count()
        total_trips = db.query(Trip).count()
        
        # Agent stats
        agent_runs = db.query(
            AgentRun.status, 
            func.count(AgentRun.id)
        ).group_by(AgentRun.status).all()
        
        # Format agent stats
        run_stats = {status: count for status, count in agent_runs}
        total_runs = sum(run_stats.values())
        success_rate = 0.0
        if total_runs > 0:
            successes = run_stats.get("success", 0)
            success_rate = round((successes / total_runs) * 100, 2)

        return {
            "total_users": total_users,
            "total_trips": total_trips,
            "agent_runs": {
                "total": total_runs,
                "by_status": run_stats,
                "success_rate_percent": success_rate
            }
        }
    except Exception as e:
        logger.exception("Failed to generate admin stats")
        raise VoyagerError("Failed to fetch admin statistics")
