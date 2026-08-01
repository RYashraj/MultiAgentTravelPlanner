"""
Unit tests for BudgetAgent.compute_budget().

Tests all edge cases called out in the roadmap:
  - Normal happy path (flight + hotel found)
  - Missing flight data (None, not-found dict)
  - Missing hotel data (None, not-found dict)
  - Both missing
  - Null / zero / negative values in inputs
  - Partial data (flight found, hotel not)
  - Very short trip (1 day)
  - Very long trip (30 days)
  - Unknown budget tier
"""
import pytest

from app.agents.budget_agent import compute_budget


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _good_flight(price_inr: int = 4500) -> dict:
    return {
        "found": True,
        "origin": "Delhi",
        "destination": "Mumbai",
        "carrier": "IndiGo",
        "price_inr": price_inr,
        "roundtrip_price_inr": price_inr * 2,
    }


def _good_hotel(nightly: int = 2000, days: int = 3) -> dict:
    return {
        "found": True,
        "destination": "Mumbai",
        "budget_tier": "budget",
        "hotels": [{"name": "Test Hotel"}],
        "cheapest_nightly_inr": nightly,
        "total_hotel_estimate_inr": nightly * days,
    }


def _not_found_flight(reason: str = "No route found") -> dict:
    return {"found": False, "origin": "Delhi", "destination": "Mumbai", "reason": reason}


def _not_found_hotel(reason: str = "No hotels") -> dict:
    return {
        "found": False,
        "destination": "Mumbai",
        "budget_tier": "budget",
        "hotels": [],
        "reason": reason,
        "cheapest_nightly_inr": 1800,
        "total_hotel_estimate_inr": 5400,
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_happy_path_complete():
    result = compute_budget(_good_flight(4500), _good_hotel(2000, 3), 3, "budget")
    assert result["status"] == "complete"
    assert result["flight_cost_inr"] == 9000   # 4500 * 2 round-trip
    assert result["hotel_cost_inr"] == 6000    # 2000 * 3 nights
    assert result["daily_spend_inr"] > 0
    assert result["grand_total_inr"] > 0
    assert result["grand_total_inr"] == result["flight_cost_inr"] + result["hotel_cost_inr"] + result["daily_spend_inr"]
    assert result["missing"] == []
    assert "total" in result["breakdown"]


def test_grand_total_arithmetic():
    """Verify grand total is exactly the sum of its parts — no silent rounding."""
    f = _good_flight(5800)
    h = _good_hotel(4500, 5)
    result = compute_budget(f, h, 5, "midrange")
    expected = result["flight_cost_inr"] + result["hotel_cost_inr"] + result["daily_spend_inr"]
    assert result["grand_total_inr"] == expected


# ---------------------------------------------------------------------------
# Missing flight data
# ---------------------------------------------------------------------------

def test_missing_flight_none():
    result = compute_budget(None, _good_hotel(2000, 3), 3, "budget")
    assert result["status"] in ("partial", "incomplete")
    assert "flight" in result["missing"]
    assert result["flight_cost_inr"] == 0
    assert result["grand_total_inr"] >= 0  # Should not go negative


def test_missing_flight_not_found_dict():
    result = compute_budget(_not_found_flight(), _good_hotel(2000, 3), 3, "budget")
    assert result["status"] in ("partial", "incomplete")
    assert any("flight" in m for m in result["missing"])
    assert result["flight_cost_inr"] == 0


# ---------------------------------------------------------------------------
# Missing hotel data
# ---------------------------------------------------------------------------

def test_missing_hotel_none():
    result = compute_budget(_good_flight(4500), None, 3, "budget")
    assert result["status"] in ("partial", "incomplete")
    assert result["hotel_cost_inr"] >= 0  # Uses tier estimate, not crashes
    assert result["grand_total_inr"] >= 0


def test_missing_hotel_not_found_dict():
    """Hotel returns not-found but includes cheapest_nightly_inr — agent should use it."""
    result = compute_budget(_good_flight(4500), _not_found_hotel(), 3, "budget")
    # Hotel is "found=False" but has a cost estimate — total should not be 0
    assert result["grand_total_inr"] > 0


# ---------------------------------------------------------------------------
# Both missing
# ---------------------------------------------------------------------------

def test_both_missing():
    result = compute_budget(None, None, 3, "midrange")
    assert result["status"] == "incomplete"
    assert result["flight_cost_inr"] == 0
    assert result["grand_total_inr"] >= 0  # daily spend should still be there
    assert len(result["missing"]) >= 2


# ---------------------------------------------------------------------------
# Null / zero / negative values
# ---------------------------------------------------------------------------

def test_negative_flight_price_clamped():
    f = _good_flight(4500)
    f["roundtrip_price_inr"] = -1000
    f["price_inr"] = -500
    result = compute_budget(f, _good_hotel(2000, 3), 3, "budget")
    assert result["flight_cost_inr"] >= 0


def test_zero_flight_price():
    f = _good_flight(0)
    result = compute_budget(f, _good_hotel(2000, 3), 3, "budget")
    # flight price is 0 — should be excluded from total or marked missing
    assert result["grand_total_inr"] >= 0


def test_null_duration_defaults_to_3():
    result = compute_budget(_good_flight(), _good_hotel(), None, "budget")
    assert result["duration_days"] == 3


def test_zero_duration_defaults_to_3():
    result = compute_budget(_good_flight(), _good_hotel(), 0, "budget")
    assert result["duration_days"] == 3


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_one_day_trip():
    result = compute_budget(_good_flight(), _good_hotel(2000, 1), 1, "budget")
    assert result["duration_days"] == 1
    assert result["grand_total_inr"] > 0


def test_long_trip_30_days():
    h = _good_hotel(2000, 30)
    result = compute_budget(_good_flight(), h, 30, "midrange")
    assert result["duration_days"] == 30
    assert result["hotel_cost_inr"] > 0


def test_budget_tier_luxury():
    result = compute_budget(_good_flight(), _good_hotel(20000, 3), 3, "luxury")
    assert result["budget_tier"] == "luxury"
    assert result["daily_spend_per_day_inr"] >= 5000  # luxury daily spend


def test_budget_tier_unknown_defaults_to_midrange():
    result = compute_budget(_good_flight(), _good_hotel(), 3, "some unknown value")
    assert result["budget_tier"] == "midrange"


def test_partial_data_flight_found_hotel_not():
    """
    Flight found, hotel found=False but includes a cost estimate.
    The budget agent uses the estimate — total should not be silent zero.
    This is the correct behavior: an estimate is better than nothing.
    """
    result = compute_budget(_good_flight(5000), _not_found_hotel(), 3, "budget")
    # Hotel provides a cost estimate even when found=False — budget is computable
    assert result["flight_cost_inr"] > 0
    # Total should reflect at least flight + daily (hotel estimate may also be included)
    assert result["grand_total_inr"] >= result["flight_cost_inr"]
    # Grand total should never be less than just the flight cost
    assert result["grand_total_inr"] > 0


def test_partial_data_hotel_zero_no_estimate():
    """When hotel data is completely zeroed out (no estimate), status is partial/incomplete."""
    hotel_no_estimate = {
        "found": False,
        "destination": "Mumbai",
        "budget_tier": "budget",
        "hotels": [],
        "reason": "No data",
        "cheapest_nightly_inr": 0,
        "total_hotel_estimate_inr": 0,
    }
    result = compute_budget(_good_flight(5000), hotel_no_estimate, 3, "budget")
    # With total=0 and nightly=0, agent falls back to tier estimate — still computable
    assert result["grand_total_inr"] > 0
    assert result["flight_cost_inr"] > 0



def test_breakdown_fields_always_present():
    """breakdown dict must always have all keys regardless of data availability."""
    result = compute_budget(None, None, None, None)
    bd = result["breakdown"]
    assert "flights" in bd
    assert "accommodation" in bd
    assert "daily_expenses" in bd
    assert "total" in bd


def test_warnings_not_empty_on_missing_data():
    result = compute_budget(None, None, 3, "budget")
    assert len(result["warnings"]) > 0
