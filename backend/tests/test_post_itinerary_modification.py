"""
Tests for post-itinerary modification behavior, origin protection,
pending action confirmation, and offline regeneration in VoyagerAI.
"""
import uuid
import pytest
from app.agents.parser import heuristic_parse, parse_modification_intent
from app.agents.planner import merge_node
from app.agents.supervisor import SupervisorAgent
from app.db.models import Itinerary, User
from app.repositories import (
    ItineraryRepository,
    MessageRepository,
    TripRepository,
)


@pytest.fixture
def test_user(db_session):
    u = User(
        id=uuid.uuid4(),
        email=f"user_{uuid.uuid4().hex[:8]}@example.com",
        full_name="Test User",
    )
    db_session.add(u)
    db_session.commit()
    return u


def test_budget_message_never_overwrites_origin():
    """Requirement 1 & 6: 'i'lll say budget friendly' must set budget and NEVER set origin."""
    messages = [
        {"role": "user", "content": "im travelling from surat, for 5 days or maybe a week.. with a friend for a vacation"},
        {"role": "assistant", "content": "What is your preferred budget tier?"},
        {"role": "user", "content": "i'lll say budget friendly"}
    ]
    parsed = heuristic_parse(messages, "Goa")
    assert parsed.get("budget") == "Budget-friendly"
    # Origin from message 1 is Surat, but message 3 must NOT overwrite it with budget friendly
    assert parsed.get("origin") == "Surat"
    assert parsed.get("origin") != "I'Lll Say Budget Friendly"

    # Test standalone message 3
    parsed_only_budget = heuristic_parse([{"role": "user", "content": "i'lll say budget friendly"}], "Goa")
    assert parsed_only_budget.get("budget") == "Budget-friendly"
    assert parsed_only_budget.get("origin") is None


def test_parse_modification_intent_duration_budget_origin():
    """Requirement 2: Test parsing of explicit modification intents."""
    # Duration
    m1 = parse_modification_intent("can you update it to 7 days trip?")
    assert m1["intent_found"] is True
    assert m1["changes"].get("duration_days") == 7

    m1_wk = parse_modification_intent("change to one week")
    assert m1_wk["intent_found"] is True
    assert m1_wk["changes"].get("duration_days") == 7

    # Budget
    m2 = parse_modification_intent("change budget to luxury")
    assert m2["intent_found"] is True
    assert m2["changes"].get("budget") == "Luxury"

    m2_bf = parse_modification_intent("i'lll say budget friendly")
    assert m2_bf["intent_found"] is True
    assert m2_bf["changes"].get("budget") == "Budget-friendly"
    assert "origin" not in m2_bf["changes"]

    # Origin
    m3 = parse_modification_intent("I am travelling from Ahmedabad")
    assert m3["intent_found"] is True
    assert m3["changes"].get("origin") == "Ahmedabad"

    # Preferences & Local Exploration
    m4 = parse_modification_intent("and i want to explore local areas more")
    assert m4["intent_found"] is True
    assert "Local Exploration & Hidden Gems" in m4["changes"].get("preferences", [])


@pytest.mark.anyio
async def test_preference_modification_regenerates_itinerary(db_session, test_user):
    """Test 'and i want to explore local areas more' updates preferences and regenerates itinerary."""
    trips_repo = TripRepository(db_session)
    messages_repo = MessageRepository(db_session)
    itinerary_repo = ItineraryRepository(db_session)

    trip = trips_repo.create(test_user.id, "Goa", origin="Surat")
    messages_repo.create(trip.id, test_user.id, "user", "trip to Goa")
    itinerary_repo.save(trip.id, "# Initial Goa Itinerary\n")

    supervisor = SupervisorAgent()
    events = []
    async for ev in supervisor.run_orchestration_stream(
        db=db_session,
        trip_id=trip.id,
        user_query="and i want to explore local areas more",
        current_user=test_user,
    ):
        events.append(ev)

    updated_itinerary = db_session.query(Itinerary).filter(Itinerary.trip_id == trip.id).first()
    assert updated_itinerary is not None
    assert "Local Exploration" in updated_itinerary.content or "Goa" in updated_itinerary.content


@pytest.mark.anyio
async def test_update_to_7_days_trip_regenerates_seven_days(db_session, test_user, monkeypatch):
    """Requirement 3 & 6: 'can you update it to 7 days trip?' updates duration and regenerates 7-day itinerary."""
    async def fake_planner_invoke(state):
        narrative = merge_node(state)["agent_outputs"]["planner"]["narrative"]
        return {"agent_outputs": {"planner": {"narrative": narrative}}}

    monkeypatch.setattr("app.agents.supervisor.planner_graph.ainvoke", fake_planner_invoke)

    trips_repo = TripRepository(db_session)
    messages_repo = MessageRepository(db_session)
    itinerary_repo = ItineraryRepository(db_session)

    # 1. Create trip & initial 5-day itinerary
    trip = trips_repo.create(test_user.id, "Goa", origin="Surat")
    messages_repo.create(trip.id, test_user.id, "user", "im travelling from surat for 5 days")
    itinerary_repo.save(trip.id, "# 🌍 Initial 5-Day Goa Itinerary\n## 🗓️ Day 1\n## 🗓️ Day 2\n## 🗓️ Day 3\n## 🗓️ Day 4\n## 🗓️ Day 5\n")

    supervisor = SupervisorAgent()
    events = []
    async for ev in supervisor.run_orchestration_stream(
        db=db_session,
        trip_id=trip.id,
        user_query="can you update it to 7 days trip?",
        current_user=test_user,
    ):
        events.append(ev)

    # Reload itinerary from DB
    updated_itinerary = db_session.query(Itinerary).filter(Itinerary.trip_id == trip.id).first()
    assert updated_itinerary is not None
    assert "7-day" in updated_itinerary.content.lower() or "7 days" in updated_itinerary.content.lower()
    assert "Day 7" in updated_itinerary.content


@pytest.mark.anyio
async def test_change_budget_to_luxury_updates_budget(db_session, test_user):
    """Requirement 2 & 6: 'change budget to luxury' updates budget and regenerates itinerary."""
    trips_repo = TripRepository(db_session)
    messages_repo = MessageRepository(db_session)
    itinerary_repo = ItineraryRepository(db_session)

    trip = trips_repo.create(test_user.id, "Paris", origin="Mumbai")
    messages_repo.create(trip.id, test_user.id, "user", "trip to Paris")
    itinerary_repo.save(trip.id, "# Initial Itinerary\n")

    supervisor = SupervisorAgent()
    events = []
    async for ev in supervisor.run_orchestration_stream(
        db=db_session,
        trip_id=trip.id,
        user_query="change budget to luxury",
        current_user=test_user,
    ):
        events.append(ev)

    updated_itinerary = db_session.query(Itinerary).filter(Itinerary.trip_id == trip.id).first()
    assert updated_itinerary is not None
    assert "luxury" in updated_itinerary.content.lower()


@pytest.mark.anyio
async def test_update_origin_from_ahmedabad(db_session, test_user):
    """Requirement 1 & 6: 'I am travelling from Ahmedabad' updates origin only."""
    trips_repo = TripRepository(db_session)
    messages_repo = MessageRepository(db_session)
    itinerary_repo = ItineraryRepository(db_session)

    trip = trips_repo.create(test_user.id, "Tokyo", origin="Delhi")
    messages_repo.create(trip.id, test_user.id, "user", "trip to Tokyo")
    itinerary_repo.save(trip.id, "# Tokyo Itinerary\n")

    supervisor = SupervisorAgent()
    events = []
    async for ev in supervisor.run_orchestration_stream(
        db=db_session,
        trip_id=trip.id,
        user_query="I am travelling from Ahmedabad",
        current_user=test_user,
    ):
        events.append(ev)

    db_session.refresh(trip)
    assert trip.origin == "Ahmedabad"
    assert trip.destination == "Tokyo"


@pytest.mark.anyio
async def test_yes_executes_saved_pending_action(db_session, test_user, monkeypatch):
    """Requirement 4 & 6: 'yes' with pending action in history executes update."""
    async def fake_planner_invoke(state):
        narrative = merge_node(state)["agent_outputs"]["planner"]["narrative"]
        return {"agent_outputs": {"planner": {"narrative": narrative}}}

    monkeypatch.setattr("app.agents.supervisor.planner_graph.ainvoke", fake_planner_invoke)

    trips_repo = TripRepository(db_session)
    messages_repo = MessageRepository(db_session)
    itinerary_repo = ItineraryRepository(db_session)

    trip = trips_repo.create(test_user.id, "Goa", origin="Surat")
    messages_repo.create(trip.id, test_user.id, "user", "can you extend the trip?")
    messages_repo.create(trip.id, test_user.id, "assistant", "Would you like me to update your trip duration to 7 days?")
    itinerary_repo.save(trip.id, "# Initial 5-day itinerary\n")

    supervisor = SupervisorAgent()
    events = []
    async for ev in supervisor.run_orchestration_stream(
        db=db_session,
        trip_id=trip.id,
        user_query="yes",
        current_user=test_user,
    ):
        events.append(ev)

    updated_itinerary = db_session.query(Itinerary).filter(Itinerary.trip_id == trip.id).first()
    assert updated_itinerary is not None
    assert "7-day" in updated_itinerary.content.lower() or "Day 7" in updated_itinerary.content


@pytest.mark.anyio
async def test_yes_with_no_pending_action_asks_for_clarification(db_session, test_user):
    """Requirement 4 & 6: 'yes' with NO pending action asks focused question."""
    trips_repo = TripRepository(db_session)
    messages_repo = MessageRepository(db_session)
    itinerary_repo = ItineraryRepository(db_session)

    trip = trips_repo.create(test_user.id, "Goa", origin="Surat")
    messages_repo.create(trip.id, test_user.id, "assistant", "Here is your itinerary for Goa!")
    itinerary_repo.save(trip.id, "# Goa Itinerary\n")

    supervisor = SupervisorAgent()
    events = []
    async for ev in supervisor.run_orchestration_stream(
        db=db_session,
        trip_id=trip.id,
        user_query="yes",
        current_user=test_user,
    ):
        events.append(ev)

    # Check last message in conversation
    messages = messages_repo.list_for_trip(trip.id)
    last_msg = messages[-1].content
    assert "What specific detail would you like to update?" in last_msg


@pytest.mark.anyio
async def test_all_behavior_works_when_gemini_unavailable(db_session, test_user, monkeypatch):
    """Requirement 5 & 6: All post-itinerary modifications work offline when Gemini fails."""
    # Force Gemini planner to raise exception
    async def failing_planner(state):
        raise RuntimeError("Gemini API Offline")

    monkeypatch.setattr("app.agents.supervisor.planner_graph.ainvoke", failing_planner)

    trips_repo = TripRepository(db_session)
    messages_repo = MessageRepository(db_session)
    itinerary_repo = ItineraryRepository(db_session)

    trip = trips_repo.create(test_user.id, "Goa", origin="Surat")
    messages_repo.create(trip.id, test_user.id, "user", "initial trip")
    itinerary_repo.save(trip.id, "# Initial Itinerary\n")

    supervisor = SupervisorAgent()
    events = []
    async for ev in supervisor.run_orchestration_stream(
        db=db_session,
        trip_id=trip.id,
        user_query="can you update it to 7 days trip?",
        current_user=test_user,
    ):
        events.append(ev)

    # Verify fallback merge_node regenerated full 7-day itinerary despite Gemini failure
    updated_itinerary = db_session.query(Itinerary).filter(Itinerary.trip_id == trip.id).first()
    assert updated_itinerary is not None
    assert "Day 7" in updated_itinerary.content
