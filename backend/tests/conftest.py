import uuid

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


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    settings = get_settings()
    original_secret = settings.supabase_jwt_secret
    settings.supabase_jwt_secret = "week-3-test-secret"
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    settings.supabase_jwt_secret = original_secret
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def mock_planner_graph_stream(monkeypatch):
    from app.agents.planner import planner_graph
    from app.agents.supervisor import SupervisorAgent
    
    def fake_stream(state, *args, **kwargs):
        class FakeChunk:
            def __init__(self, content):
                self.content = content
        
        yield {"some_step": state}
        yield {
            "merge": {
                "agent_outputs": {
                    "planner": {
                        "narrative_stream": [FakeChunk("Planning has started for "), FakeChunk(state.get("destination", "unknown"))],
                        "narrative": "Planning has started for " + state.get("destination", "unknown")
                    }
                }
            }
        }
    
    async def fake_run_orchestration_stream(self, db, trip_id, user_message, user):
        from app.db.models import Itinerary, AgentRun
        itinerary = Itinerary(trip_id=trip_id, content="Day 1: Test")
        db.add(itinerary)
        agent_run = AgentRun(trip_id=trip_id, agent_name="CoordinatorAgent", status="completed", output_payload={"logs": [1,2,3,4,5]})
        db.add(agent_run)
        db.commit()

        yield {"event": "agent_log", "data": "log"}
        yield {"event": "message_chunk", "data": "chunk"}
        yield {"event": "message_complete", "data": "complete"}
        
    monkeypatch.setattr(planner_graph, "stream", fake_stream)
    monkeypatch.setattr(SupervisorAgent, "run_orchestration_stream", fake_run_orchestration_stream)

@pytest.fixture()
def auth_headers():
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "email": "traveler@example.com", "aud": "authenticated"},
        "week-3-test-secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}

