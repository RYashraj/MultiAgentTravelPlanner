import uuid
import pytest
from app.agents.supervisor import SupervisorAgent
from app.db.models import User, Trip, Itinerary, AgentRun
from tests.test_trips import TestSessionLocal, headers

@pytest.mark.anyio
async def test_supervisor_agent_orchestration():
    # Setup test session
    db = TestSessionLocal()
    try:
        # 1. Create a test user
        email = "agents-test@example.com"
        mock_id = uuid.uuid5(uuid.NAMESPACE_DNS, email)
        user = db.query(User).filter(User.id == mock_id).first()
        if not user:
            user = User(id=mock_id, email=email, full_name="Agents Test User")
            db.add(user)
            db.commit()

        # 2. Create a test trip
        trip = Trip(user_id=user.id, destination="London", status="planning")
        db.add(trip)
        db.commit()
        db.refresh(trip)

        # 3. Instantiate SupervisorAgent
        agent = SupervisorAgent()
        
        # 4. Consume the orchestration stream
        steps = []
        async for step in agent.run_orchestration_stream(db, trip.id, "Plan a trip to London", user):
            steps.append(step)

        # 5. Verify the generated steps
        assert len(steps) > 0
        events = [step["event"] for step in steps]
        assert "agent_log" in events
        assert "message_chunk" in events
        assert "message_complete" in events

        # 6. Verify database records are created
        itinerary = db.query(Itinerary).filter(Itinerary.trip_id == trip.id).first()
        assert itinerary is not None
        assert itinerary.title == "Complete Itinerary for London"
        assert "Day 1" in itinerary.description

        agent_run = db.query(AgentRun).filter(AgentRun.trip_id == trip.id).first()
        assert agent_run is not None
        assert agent_run.agent_name == "SupervisorAgent"
        assert agent_run.status == "completed"
        assert len(agent_run.logs) == 5  # We logged 5 items inside the run

    finally:
        db.close()
