import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.repositories import MessageRepository, TripRepository, UserRepository


def test_user_trip_and_message_repositories_crud():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    user_id = uuid.uuid4()
    with Session(engine) as db:
        user = UserRepository(db).upsert(user_id, "repo@example.com", "Repository Test")
        assert user.email == "repo@example.com"

        trip = TripRepository(db).create(user.id, "Kyoto")
        assert TripRepository(db).get_for_user(trip.id, user.id) is not None

        message = MessageRepository(db).create(trip.id, user.id, "user", "Plan a quiet weekend")
        assert MessageRepository(db).list_for_trip(trip.id)[0].id == message.id
    Base.metadata.drop_all(engine)
