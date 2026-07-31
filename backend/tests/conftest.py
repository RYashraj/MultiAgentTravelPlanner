
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app

# Create a module-level engine for tests
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)

@pytest.fixture()
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture()
def client():
    settings = get_settings()
    original_secret = settings.supabase_jwt_secret
    settings.supabase_jwt_secret = "week-3-test-secret"
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    settings.supabase_jwt_secret = original_secret

@pytest.fixture(autouse=True)
def mock_agent_calls(monkeypatch):
    """Mock Gemini API calls so tests run fast and offline."""
    from app.agents import coordinator, planner, supervisor

    async def fake_parse_state(messages, destination):
        # Always return a complete state to bypass gating
        return {
            "origin": "Test City",
            "destination": destination,
            "budget": "$5000",
            "duration_days": 3,
            "dates": "Next month",
            "goal": "Relaxation",
            "preferences": ["Food"],
        }
    
    def fake_coordinator_invoke(state):
        return {
            "agent_outputs": {
                "coordinator": {
                    "status": "planning_started",
                    "trip_context": {
                        "origin": state.get("origin"),
                        "destination": state.get("destination", "Test"),
                        "budget": state.get("budget"),
                        "dates": state.get("dates"),
                        "preferences": state.get("preferences", [])
                    }
                }
            }
        }

    def fake_planner_invoke(state):
        return {
            "agent_outputs": {
                "planner": {
                    "narrative": "# Test Itinerary\nDay 1: Testing",
                    "gemini_used": False
                }
            }
        }

    async def fake_coordinator_ainvoke(state, *args, **kwargs):
        return fake_coordinator_invoke(state)

    async def fake_planner_ainvoke(state, *args, **kwargs):
        return fake_planner_invoke(state)

    monkeypatch.setattr(supervisor, "parse_travel_state", fake_parse_state)
    monkeypatch.setattr(coordinator.coordinator_graph, "invoke", fake_coordinator_invoke)
    monkeypatch.setattr(planner.planner_graph, "invoke", fake_planner_invoke)
    monkeypatch.setattr(coordinator.coordinator_graph, "ainvoke", fake_coordinator_ainvoke)
    monkeypatch.setattr(planner.planner_graph, "ainvoke", fake_planner_ainvoke)

@pytest.fixture()
def auth_headers():
    static_id = "12345678-1234-5678-1234-567812345678"
    token = jwt.encode(
        {"sub": static_id, "email": "traveler@example.com", "aud": "authenticated"},
        "week-3-test-secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}
