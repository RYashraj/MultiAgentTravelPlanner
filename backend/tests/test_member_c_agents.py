"""
Tests for Member C Stretch Features: TransportAgent & FoodAgent
Verifies fallback behavior, estimate disclosure, and non-crashing execution.
"""
from app.agents.transport_agent import get_transport_options
from app.agents.food_agent import get_food_recommendations


def test_transport_agent_fallback():
    # Test valid destination with local fallback
    res = get_transport_options(destination="Jaipur", origin="Delhi", budget="midrange", duration_days=4)
    assert res["found"] is True
    assert res["destination"] == "Jaipur"
    assert "summary" in res
    assert "airport_transfer" in res
    assert "local_transit" in res
    assert isinstance(res["local_transit"], list)
    assert res["estimated_daily_cost_inr"] > 0
    assert res["total_transport_estimate_inr"] == res["estimated_daily_cost_inr"] * 4
    # Ensure source indicator exists
    assert res["source"] in ("ai", "local_db")


def test_transport_agent_missing_destination():
    res = get_transport_options(destination="")
    assert res["found"] is False
    assert "Destination not specified" in res["reason"]


def test_food_agent_fallback():
    # Test valid destination with local fallback
    res = get_food_recommendations(destination="Udaipur", budget="luxury", duration_days=3, dietary_preferences=["Vegetarian"])
    assert res["found"] is True
    assert res["destination"] == "Udaipur"
    assert "summary" in res
    assert "must_try_dishes" in res
    assert isinstance(res["must_try_dishes"], list)
    assert "recommended_places" in res
    assert isinstance(res["recommended_places"], list)
    assert res["estimated_daily_food_cost_inr"] > 0
    assert res["total_food_estimate_inr"] == res["estimated_daily_food_cost_inr"] * 3
    assert res["source"] in ("ai", "local_db")


def test_food_agent_missing_destination():
    res = get_food_recommendations(destination=" ")
    assert res["found"] is False
    assert "Destination not specified" in res["reason"]
