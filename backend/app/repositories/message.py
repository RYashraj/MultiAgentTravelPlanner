from sqlalchemy.orm import Session
from app.db.models import Message
import uuid

class MessageRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_trip(self, trip_id: uuid.UUID) -> list[Message]:
        return self.db.query(Message).filter(Message.trip_id == trip_id).order_by(Message.created_at.asc()).all()

    def create(self, trip_id: uuid.UUID, sender: str, content: str) -> Message:
        message = Message(trip_id=trip_id, sender=sender, content=content)
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message
