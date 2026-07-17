# pyrefly: ignore [missing-import]
import pytest
import uuid
from fastapi.testclient import TestClient
# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine
# pyrefly: ignore [missing-import]
from sqlalchemy.pool import StaticPool
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import sessionmaker

from app.db.session import get_db
from app.db.base import Base
from app.db.models import User, Trip, Message
from app.main import app

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()

# Create tables in test DB
Base.metadata.create_all(bind=test_engine)

@pytest.fixture(autouse=True, scope="module")
def setup_database():
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)

client = TestClient(app)

# Use a mock authorization header for testing
headers = {
    "Authorization": "Bearer mock-user-testuser@example.com"
}

def test_create_trip():
    # Test unauthorized request
    response = client.post("/api/v1/trips", json={"destination": "Tokyo"})
    assert response.status_code == 401

    # Test authorized request
    response = client.post(
        "/api/v1/trips", 
        json={"destination": "Tokyo"},
        headers=headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["destination"] == "Tokyo"
    assert body["status"] == "draft"
    assert "id" in body


def test_list_trips():
    # Insert multiple trips for the user
    client.post("/api/v1/trips", json={"destination": "Paris"}, headers=headers)
    client.post("/api/v1/trips", json={"destination": "Rome"}, headers=headers)

    response = client.get("/api/v1/trips", headers=headers)
    assert response.status_code == 200
    trips = response.json()
    assert len(trips) >= 2
    # Ensure they belong to the user
    for trip in trips:
        assert trip["destination"] in ["Tokyo", "Paris", "Rome"]


def test_send_and_get_messages():
    # 1. Create a trip
    trip_res = client.post("/api/v1/trips", json={"destination": "London"}, headers=headers)
    trip_id = trip_res.json()["id"]

    # 2. Post a message (non-stream)
    msg_res = client.post(
        f"/api/v1/trips/{trip_id}/messages", 
        json={"content": "Please suggest a 3-day plan"},
        headers=headers
    )
    assert msg_res.status_code == 200
    body = msg_res.json()
    assert "user_message" in body
    assert "coordinator_message" in body
    assert body["user_message"]["content"] == "Please suggest a 3-day plan"
    assert "VoyagerAI" in body["coordinator_message"]["content"]

    # 3. Retrieve messages
    list_res = client.get(f"/api/v1/trips/{trip_id}/messages", headers=headers)
    assert list_res.status_code == 200
    messages = list_res.json()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


def test_stream_message():
    # 1. Create a trip
    trip_res = client.post("/api/v1/trips", json={"destination": "Berlin"}, headers=headers)
    trip_id = trip_res.json()["id"]

    # 2. Post a message with stream=True
    response = client.post(
        f"/api/v1/trips/{trip_id}/messages?stream=true",
        json={"content": "Suggest historical sites"},
        headers=headers
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    
    # Read the streamed lines
    lines = [line for line in response.iter_lines()]
    # Check that we have event stream items
    has_chunk = any("message_chunk" in line for line in lines)
    has_user_msg = any("user_message" in line for line in lines)
    has_complete = any("message_complete" in line for line in lines)
    
    assert has_user_msg
    assert has_chunk
    assert has_complete
