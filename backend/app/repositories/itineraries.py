import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.models import Itinerary


class ItineraryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_for_trip(self, trip_id: uuid.UUID) -> Itinerary | None:
        return self.db.scalar(select(Itinerary).where(Itinerary.trip_id == trip_id))

    def save(self, trip_id: uuid.UUID, content: str) -> Itinerary:
        itinerary = self.get_for_trip(trip_id)
        if itinerary is None:
            itinerary = Itinerary(trip_id=trip_id, content=content, status="planning")
            self.db.add(itinerary)
        else:
            itinerary.content = content
        self.db.commit()
        self.db.refresh(itinerary)
        return itinerary
