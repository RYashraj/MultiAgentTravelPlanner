import uuid
import pytest
from app.agents.parser import heuristic_parse, parse_travel_state
from app.agents.planner import merge_node
from app.agents.supervisor import SupervisorAgent
from app.db.models import Itinerary, User
from app.repositories import MessageRepository, TripRepository
from app.tools.places_tool import get_transport_info


def test_heuristic_parse_destination_and_duration_regression():
    """
    Regression test for:
    1. Destination remains Tokyo even when user says 'luxury, for 2 weeks and for travelling'
    2. '2 weeks' is converted to 14 days
    3. 'travelling' is parsed as goal (Exploration) and NOT destination
    """
    messages = [
        {"role": "user", "content": "india"},
        {"role": "user", "content": "luxury, for 2 weeks and for travelling"},
    ]
    parsed = heuristic_parse(messages, destination="Tokyo, Japan")

    assert parsed["destination"] == "Tokyo, Japan"
    assert parsed["origin"] == "India"
    assert parsed["duration_days"] == 14
    assert parsed["budget"] == "Luxury"
    assert parsed["goal"] in ("Exploration", "Travel")


@pytest.mark.anyio
async def test_parse_travel_state_never_overwrites_with_generic_words():
    """
    Regression test ensuring parse_travel_state never sets destination to 'Travelling'.
    """
    messages = [
        {"role": "user", "content": "india"},
        {"role": "user", "content": "luxury, for 2 weeks and for travelling"},
        {"role": "user", "content": "14 days"},
    ]
    state = await parse_travel_state(messages, destination="Tokyo, Japan")

    assert state["destination"] in ("Tokyo, Japan", "Tokyo")
    assert state["destination"] != "Travelling"
    assert state["duration_days"] == 14


def test_planner_14_day_itinerary_and_international_tips():
    """
    Regression test for:
    1. Planner generating all 14 days (removing 7-day hardcoded cap)
    2. Travel tips and transport excluding India-only suggestions (IRCTC, Jio, redBus) for Tokyo
    """
    state = {
        "destination": "Tokyo, Japan",
        "origin": "Ahmedabad",
        "dates": "Summer",
        "budget": "Luxury",
        "goal": "Exploration",
        "duration_days": 14,
        "preferences": ["streetwear shopping", "food"],
        "memory_context": [],
        "agent_outputs": {},
    }
    result = merge_node(state)
    narrative = result["agent_outputs"]["planner"]["narrative"]

    # Verify all 14 days are present
    for day_num in range(1, 15):
        assert f"Day {day_num}" in narrative, f"Expected Day {day_num} in itinerary"

    # Verify international travel tips (no IRCTC, redBus, Jio/Airtel for Tokyo)
    assert "IRCTC" not in narrative
    assert "redBus" not in narrative
    assert "Jio/Airtel" not in narrative
    assert "eSIM" in narrative or "Google Flights" in narrative or "Skyscanner" in narrative


def test_transport_info_international_awareness():
    """
    Test get_transport_info for international destinations.
    """
    transport = get_transport_info("Ahmedabad", "Tokyo, Japan")
    assert "IRCTC" not in transport
    assert "redBus" not in transport
    assert "Google Flights" in transport or "Skyscanner" in transport


def test_supervisor_minimal_fallback_with_origin_update():
    """
    Test SupervisorAgent minimal fallback when Gemini is unavailable during post-itinerary follow-up.
    """
    fallback = SupervisorAgent._minimal_fallback("Tokyo, Japan", "i am travelling from ahmedabad")
    assert "Ahmedabad" in fallback
    assert "Tokyo, Japan" in fallback
    assert "Google Flights" in fallback or "Skyscanner" in fallback


@pytest.mark.anyio
async def test_full_reproduction_conversation_flow(db_session, monkeypatch):
    """
    Test full reproduction flow using actual parse_travel_state.
    """
    # Unpatch parse_travel_state to use actual parsing logic
    monkeypatch.undo()

    user = User(id=uuid.uuid4(), email="repro_user@example.com", full_name="Repro User")
    db_session.add(user)
    db_session.commit()

    trip_repo = TripRepository(db_session)
    msg_repo = MessageRepository(db_session)

    # 1. Create trip to Tokyo, Japan
    trip = trip_repo.create(user.id, "Tokyo, Japan")
    assert trip.destination == "Tokyo, Japan"

    supervisor = SupervisorAgent()

    # Step 1: User says 'india'
    msg_repo.create(trip.id, user.id, "user", "india")
    events_1 = []
    async for event in supervisor.run_orchestration_stream(db_session, trip.id, "india", user):
        events_1.append(event)
    db_session.refresh(trip)
    assert trip.destination == "Tokyo, Japan"

    # Step 2: User says 'luxury, for 2 weeks and for travelling'
    msg_repo.create(trip.id, user.id, "user", "luxury, for 2 weeks and for travelling")
    events_2 = []
    async for event in supervisor.run_orchestration_stream(db_session, trip.id, "luxury, for 2 weeks and for travelling", user):
        events_2.append(event)
    db_session.refresh(trip)
    assert trip.destination == "Tokyo, Japan"
    assert trip.destination != "Travelling"

    # Step 3: Check fallback itinerary generation for 14 days
    state = {
        "destination": trip.destination,
        "origin": "India",
        "dates": "Flexible",
        "budget": "Luxury",
        "goal": "Exploration",
        "duration_days": 14,
        "preferences": [],
        "memory_context": [],
        "agent_outputs": {},
    }
    planned = merge_node(state)
    narrative = planned["agent_outputs"]["planner"]["narrative"]
    assert "Day 14" in narrative
    assert "IRCTC" not in narrative

    # Step 4: Post-itinerary follow-up fallback with origin update
    followup = SupervisorAgent._minimal_fallback(trip.destination, "i am travelling from ahmedabad")
    assert "Ahmedabad" in followup
    assert "Google Flights" in followup or "Skyscanner" in followup
