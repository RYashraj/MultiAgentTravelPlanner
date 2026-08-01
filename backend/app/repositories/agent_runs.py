import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import AgentRun


class AgentRunRepository:
    def __init__(self, db: Session): self.db = db
    def start(self, trip_id: uuid.UUID, input_payload: dict) -> AgentRun:
        run = AgentRun(trip_id=trip_id, agent_name="CoordinatorAgent", status="running", input_payload=input_payload)
        self.db.add(run); self.db.commit(); self.db.refresh(run)
        return run
    def complete(self, run: AgentRun, output_payload: dict) -> AgentRun:
        run.status = "completed"; run.output_payload = output_payload; run.completed_at = datetime.now(timezone.utc)
        self.db.commit(); self.db.refresh(run)
        return run
