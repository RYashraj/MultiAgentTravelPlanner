import uuid

import pytest

from app.agents.supervisor import SupervisorAgent
from app.db.models import AgentRun, Itinerary, Trip, User


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
    trip = Trip(user_id=user.id, destination="Mumbai", status="draft")
    db.add(trip)
    db.commit()
    db.refresh(trip)

    # 3. Instantiate SupervisorAgent
    agent = SupervisorAgent()

    # 4. Consume the orchestration stream (full message includes origin, budget, duration, goal
    #    so the supervisor goes into planning mode rather than requesting clarification)
    steps = []
    async for step in agent.run_orchestration_stream(
        db,
        trip.id,
        "I want to travel from Delhi to Mumbai for 3 days. Budget is Rs.30,000. Goal is sightseeing.",
        user,
    ):
        steps.append(step)

    # 5. Verify the pipeline produced events
    assert len(steps) > 0, "Supervisor should emit at least one event"
    events = [step["event"] for step in steps]
    assert "agent_log" in events, "Expected at least one agent_log event"
    # Either token+result (planning path) or clarification path — both are valid
    assert "result" in events or any(
        step.get("content", "").startswith("I'd love") for step in steps
    ), "Expected a result event or clarification message"

    # 6. If an itinerary was generated, verify it has real content
    itinerary = db.query(Itinerary).filter(Itinerary.trip_id == trip.id).first()
    if itinerary:
        assert len(itinerary.content) > 50, "Itinerary content should be substantial (not a stub)"

    # 7. Verify an agent run record was created
    agent_run = db.query(AgentRun).filter(AgentRun.trip_id == trip.id).first()
    assert agent_run is not None, "Expected an AgentRun record in the database"
    # The repository sets agent_name = "supervisor" — verify against actual value
    assert agent_run.agent_name == "supervisor", (
        f"Expected agent_name='supervisor', got {agent_run.agent_name!r}"
    )

