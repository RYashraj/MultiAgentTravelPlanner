import pytest
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.repositories.user import UserRepository
from app.repositories.trip import TripRepository
from app.repositories.message import MessageRepository

# In-memory SQLite for testing repositories
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

@pytest.fixture(scope="function", autouse=True)
def init_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)

@pytest.fixture
def db_session():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()

def test_user_repository(db_session):
    user_repo = UserRepository(db_session)
    user_id = uuid.uuid4()
    
    # 1. Create User
    user = user_repo.create(user_id=user_id, email="repo@example.com", full_name="Repo Test")
    assert user.id == user_id
    assert user.email == "repo@example.com"
    assert user.full_name == "Repo Test"

    # 2. Get User by ID
    fetched_user = user_repo.get_by_id(user_id)
    assert fetched_user is not None
    assert fetched_user.email == "repo@example.com"

    # 3. Get User by Email
    fetched_user_by_email = user_repo.get_by_email("repo@example.com")
    assert fetched_user_by_email is not None
    assert fetched_user_by_email.id == user_id


def test_trip_repository(db_session):
    trip_repo = TripRepository(db_session)
    user_id = uuid.uuid4()

    # 1. Create Trip
    trip = trip_repo.create(user_id=user_id, destination="London", status="draft")
    assert trip.destination == "London"
    assert trip.status == "draft"
    assert trip.user_id == user_id
    assert isinstance(trip.id, uuid.UUID)

    # 2. Get Trip by ID
    fetched_trip = trip_repo.get_by_id(trip.id)
    assert fetched_trip is not None
    assert fetched_trip.destination == "London"

    # 3. List Trips by User
    trip_repo.create(user_id=user_id, destination="Paris", status="ready")
    trips = trip_repo.list_by_user(user_id)
    assert len(trips) == 2
    destinations = [t.destination for t in trips]
    assert "London" in destinations
    assert "Paris" in destinations


def test_message_repository(db_session):
    message_repo = MessageRepository(db_session)
    trip_id = uuid.uuid4()

    # 1. Create message
    msg = message_repo.create(trip_id=trip_id, sender="user", content="Suggest routes")
    assert msg.sender == "user"
    assert msg.content == "Suggest routes"
    assert msg.trip_id == trip_id
    
    # 2. List messages by trip
    message_repo.create(trip_id=trip_id, sender="assistant", content="Optimal route is fly-in")
    messages = message_repo.list_by_trip(trip_id)
    assert len(messages) == 2
    assert messages[0].sender == "user"
    assert messages[1].sender == "assistant"
