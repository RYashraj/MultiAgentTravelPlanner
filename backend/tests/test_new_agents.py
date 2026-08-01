import pytest
from app.agents.flight_agent import flight_agent_node
from app.agents.hotel_agent import hotel_agent_node
from app.agents.budget_agent import budget_agent_node
from app.agents.planner import planner_graph
from app.agents.state import AgentState


@pytest.mark.anyio
async def test_flight_agent_node():
    state = AgentState(
        trip_id="test-1",
        origin="Mumbai",
        destination="Delhi",
        dates="2025-06-15",
        budget="Budget-friendly",
        goal="Vacation",
        duration_days=3,
        preferences=["food"],
        user_message="Test message",
        memory_context=[],
        agent_outputs={}
    )
    res = flight_agent_node(state)
    assert "flights" in res["agent_outputs"]
    flights_output = res["agent_outputs"]["flights"]
    assert flights_output["origin_iata"] == "BOM"
    assert flights_output["destination_iata"] == "DEL"
    assert isinstance(flights_output["flights"], list)
    assert len(flights_output["flights"]) > 0


@pytest.mark.anyio
async def test_flight_agent_node_dynamic_destinations():
    """Verify that different input origins and destinations return distinct, route-specific flight results."""
    # Test Destination 1: Tokyo
    state_tokyo = AgentState(
        trip_id="test-tokyo",
        origin="Mumbai",
        destination="Tokyo",
        dates="2025-09-01",
        budget="Standard",
        goal="Sightseeing",
        duration_days=5,
        preferences=["anime", "food"],
        user_message="Flights to Tokyo",
        memory_context=[],
        agent_outputs={}
    )
    res_tokyo = flight_agent_node(state_tokyo)["agent_outputs"]["flights"]
    assert res_tokyo["origin_iata"] == "BOM"
    assert res_tokyo["destination_iata"] == "TYO"
    assert any(f["carrier"] in ["Japan Airlines", "All Nippon Airways", "Singapore Airlines"] for f in res_tokyo["flights"])

    # Test Destination 2: Paris
    state_paris = AgentState(
        trip_id="test-paris",
        origin="Delhi",
        destination="Paris",
        dates="2025-10-10",
        budget="Standard",
        goal="Culture",
        duration_days=4,
        preferences=["art"],
        user_message="Flights to Paris",
        memory_context=[],
        agent_outputs={}
    )
    res_paris = flight_agent_node(state_paris)["agent_outputs"]["flights"]
    assert res_paris["origin_iata"] == "DEL"
    assert res_paris["destination_iata"] == "PAR"
    assert any(f["carrier"] in ["Air France", "Emirates", "Gulf Air"] for f in res_paris["flights"])



@pytest.mark.anyio
async def test_hotel_agent_node():
    state = AgentState(
        trip_id="test-2",
        origin="Mumbai",
        destination="Goa",
        dates="2025-06-15",
        budget="Luxury $5000",
        goal="Relaxation",
        duration_days=3,
        preferences=["beach"],
        user_message="Test message",
        memory_context=[],
        agent_outputs={}
    )
    res = hotel_agent_node(state)
    assert "hotels" in res["agent_outputs"]
    hotels_output = res["agent_outputs"]["hotels"]
    assert hotels_output["destination_iata"] == "GOI"
    assert hotels_output["budget_tier"] == "luxury"
    assert isinstance(hotels_output["hotels"], list)


@pytest.mark.anyio
async def test_budget_agent_node_within_budget():
    state = AgentState(
        trip_id="test-3",
        origin="Mumbai",
        destination="Delhi",
        dates="2025-06-15",
        budget="₹50,000",
        goal="Vacation",
        duration_days=3,
        preferences=["food"],
        user_message="Test message",
        memory_context=[],
        agent_outputs={
            "flights": {"cheapest_price_inr": 4500.0},
            "hotels": {"cheapest_price_inr": 3800.0},
            "places": {"attractions": [{"description": "Red Fort entry ₹50"}]}
        }
    )
    res = budget_agent_node(state)
    assert "budget_analysis" in res["agent_outputs"]
    b = res["agent_outputs"]["budget_analysis"]
    assert b["over_budget"] is False
    assert b["user_budget_inr"] == 50000.0


@pytest.mark.anyio
async def test_budget_agent_node_over_budget():
    state = AgentState(
        trip_id="test-4",
        origin="Mumbai",
        destination="Delhi",
        dates="2025-06-15",
        budget="₹5,000",
        goal="Vacation",
        duration_days=5,
        preferences=["food"],
        user_message="Test message",
        memory_context=[],
        agent_outputs={
            "flights": {"cheapest_price_inr": 5000.0},
            "hotels": {"cheapest_price_inr": 3000.0},
            "places": {"attractions": [{"description": "Special tour ₹1200"}]}
        }
    )
    res = budget_agent_node(state)
    b = res["agent_outputs"]["budget_analysis"]
    assert b["over_budget"] is True
    assert len(b["recommendations"]) > 0


@pytest.mark.anyio
async def test_planner_graph_execution():
    from app.agents.planner import _workflow
    graph = _workflow.compile()
    state = AgentState(
        trip_id="test-5",
        origin="Mumbai",
        destination="Goa",
        dates="2025-06-15",
        budget="Budget-friendly ₹15,000",
        goal="Beach vacation",
        duration_days=3,
        preferences=["beach", "seafood"],
        user_message="Plan a trip to Goa",
        memory_context=[],
        agent_outputs={}
    )
    res = await graph.ainvoke(state)
    outputs = res.get("agent_outputs", {})
    assert "weather" in outputs
    assert "places" in outputs
    assert "flights" in outputs
    assert "hotels" in outputs
    assert "budget_analysis" in outputs
    assert "planner" in outputs
    assert isinstance(outputs["planner"]["narrative"], str)
    assert len(outputs["planner"]["narrative"]) > 100


@pytest.mark.anyio
async def test_planner_graph_resilience_on_agent_failures(monkeypatch):
    """Verify that graph execution completes successfully even if Flight, Hotel, or Budget agent calls fail."""
    from app.agents import flight_agent, hotel_agent, budget_agent
    from app.agents.planner import _workflow

    # Mock tool failures in Flight and Hotel agents
    def failing_flight_search(state):
        outputs = dict(state.get("agent_outputs") or {})
        return {"agent_outputs": {**outputs, "flights": {"origin_iata": "BOM", "destination_iata": "GOI", "flights": [], "cheapest_price_str": "N/A", "cheapest_price_inr": None, "error": "API Timeout"}}}

    def failing_hotel_search(state):
        outputs = dict(state.get("agent_outputs") or {})
        return {"agent_outputs": {**outputs, "hotels": {"destination_iata": "GOI", "budget_tier": "budget", "hotels": [], "cheapest_price_str": "N/A", "cheapest_price_inr": None, "error": "Connection Refused"}}}

    monkeypatch.setattr(flight_agent, "flight_agent_node", failing_flight_search)
    monkeypatch.setattr(hotel_agent, "hotel_agent_node", failing_hotel_search)

    graph = _workflow.compile()
    state = AgentState(
        trip_id="test-resilience",
        origin="Mumbai",
        destination="Goa",
        dates="2025-06-15",
        budget="Budget-friendly ₹15,000",
        goal="Beach vacation",
        duration_days=3,
        preferences=["beach"],
        user_message="Plan a trip to Goa despite API errors",
        memory_context=[],
        agent_outputs={}
    )
    res = await graph.ainvoke(state)
    outputs = res.get("agent_outputs", {})
    
    # Verify graph completed without raising exceptions
    assert "planner" in outputs
    assert isinstance(outputs["planner"]["narrative"], str)
    assert len(outputs["planner"]["narrative"]) > 100
    assert "VoyagerAI" in outputs["planner"]["narrative"]

