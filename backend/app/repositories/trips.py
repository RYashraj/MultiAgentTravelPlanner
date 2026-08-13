import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Trip


class TripRepository:
    def __init__(self, db: Session): self.db = db
    def create(self, user_id: uuid.UUID, destination: str) -> Trip:
        trip = Trip(user_id=user_id, destination=destination, status="draft", is_saved=False)
        self.db.add(trip); self.db.commit(); self.db.refresh(trip)
        return trip
    def get_for_user(self, trip_id: uuid.UUID, user_id: uuid.UUID) -> Trip | None:
        return self.db.scalar(select(Trip).where(Trip.id == trip_id, Trip.user_id == user_id))
    def list_for_user(self, user_id: uuid.UUID, saved: bool | None = None) -> list[Trip]:
        stmt = select(Trip).where(Trip.user_id == user_id)
        if saved is not None:
            stmt = stmt.where(Trip.is_saved == saved)
        return list(self.db.scalars(stmt.order_by(Trip.created_at.desc())))
