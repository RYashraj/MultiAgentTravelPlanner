from sqlalchemy.orm import Session
from app.db.models import Trip
import uuid

class TripRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, trip_id: uuid.UUID) -> Trip | None:
        return self.db.query(Trip).filter(Trip.id == trip_id).first()

    def list_by_user(self, user_id: uuid.UUID) -> list[Trip]:
        return self.db.query(Trip).filter(Trip.user_id == user_id).order_by(Trip.created_at.desc()).all()

    def create(self, user_id: uuid.UUID, destination: str, status: str = "draft") -> Trip:
        trip = Trip(user_id=user_id, destination=destination, status=status)
        self.db.add(trip)
        self.db.commit()
        self.db.refresh(trip)
        return trip
