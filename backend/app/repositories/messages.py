import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Message


class MessageRepository:
    def __init__(self, db: Session): self.db = db
    def create(self, trip_id: uuid.UUID, user_id: uuid.UUID, role: str, content: str) -> Message:
        message = Message(trip_id=trip_id, user_id=user_id, role=role, content=content)
        self.db.add(message); self.db.commit(); self.db.refresh(message)
        return message
    def list_for_trip(self, trip_id: uuid.UUID) -> list[Message]:
        return list(self.db.scalars(select(Message).where(Message.trip_id == trip_id).order_by(Message.created_at.asc())))
