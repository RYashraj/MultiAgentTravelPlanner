import uuid
import pytest
from app.agents.supervisor import SupervisorAgent
from app.db.models import User, Trip, Itinerary, AgentRun, Message

@pytest.mark.anyio
async def test_supervisor_agent_orchestration(db_session):
    db = db_session
    # 1. Create a test user
    email = "agents-test@example.com"
    mock_id = uuid.uuid5(uuid.NAMESPACE_DNS, email)
    user = db.query(User).filter(User.id == mock_id).first()
    if not user:
        user = User(id=mock_id, email=email, full_name="Agents Test User")
        db.add(user)
        db.commit()

    # 2. Create a test trip
    trip = Trip(user_id=user.id, destination="London", status="draft")
    db.add(trip)
    db.commit()
    db.refresh(trip)

    # 3. Instantiate SupervisorAgent
    agent = SupervisorAgent()
    
    # 4. Consume the orchestration stream
    steps = []
    async for step in agent.run_orchestration_stream(db, trip.id, "Plan a relaxing 3 day vacation to London for next month with a $5000 budget", user):
        steps.append(step)

    # 5. Verify the generated steps
    assert len(steps) > 0
    events = [step["event"] for step in steps]
    assert "agent_log" in events
    assert "token" in events
    assert "result" in events

    # 6. Verify database records are created
    itinerary = db.query(Itinerary).filter(Itinerary.trip_id == trip.id).first()
    assert itinerary is not None
    assert "Test Itinerary" in itinerary.content

    agent_run = db.query(AgentRun).filter(AgentRun.trip_id == trip.id).first()
    assert agent_run is not None
    assert agent_run.agent_name == "CoordinatorAgent"
    assert agent_run.status == "completed"
