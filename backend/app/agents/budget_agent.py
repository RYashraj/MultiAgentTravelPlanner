"""
BudgetAgent: aggregates flight + hotel + daily expenses into a structured budget breakdown.

This is the most easily-wrong agent per the roadmap warning. Key design principles:
  - Never silently produce a wrong total. If data is missing, say so explicitly.
  - All inputs are validated and sanitised before arithmetic.
  - Negative or null cost components are treated as zero with a warning.
  - Returns a status field: "complete", "partial", or "incomplete".
  - Unit-testable pure functions with no I/O side effects.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Estimated daily spend by budget tier (meals + local transport + attractions)
_DAILY_SPEND: dict[str, int] = {
    "budget": 1500,
    "midrange": 3500,
    "luxury": 8000,
}


def _safe_int(value: Any, field_name: str) -> tuple[int, str | None]:
    """
    Convert a value to a non-negative integer.

    Returns (value_int, warning_message).
    warning_message is None if the value is valid.
    """
    if value is None:
        return 0, f"{field_name} is None — treated as 0"
    try:
        v = int(float(str(value)))
    except (ValueError, TypeError):
        return 0, f"{field_name} could not be parsed ({value!r}) — treated as 0"
    if v < 0:
        return 0, f"{field_name} is negative ({v}) — clamped to 0"
    return v, None


def _get_budget_tier(budget: str | None) -> str:
    b = (budget or "").lower()
    if any(w in b for w in ["luxury", "no limit", "unlimited", "5 star", "five star", "premium"]):
        return "luxury"
    if any(w in b for w in ["budget", "cheap", "low", "backpack", "hostel", "friendly"]):
        return "budget"
    return "midrange"


def compute_budget(
    flight_data: dict[str, Any] | None,
    hotel_data: dict[str, Any] | None,
    duration_days: int | None,
    budget_str: str | None,
) -> dict[str, Any]:
    """
    Compute a full budget breakdown from flight, hotel, and daily spend estimates.

    Args:
        flight_data:  Output from FlightAgent.get_flight_options() (or None).
        hotel_data:   Output from HotelAgent.get_hotel_options() (or None).
        duration_days: Trip length in days (or None).
        budget_str:   Raw budget string from user (used for tier classification).

    Returns:
        Dict with:
          flight_cost_inr         — round-trip flight cost (0 if unavailable)
          hotel_cost_inr          — total hotel cost for duration (0 if unavailable)
          daily_spend_inr         — per-day estimate x duration
          grand_total_inr         — sum of all components
          daily_spend_per_day_inr — per-day budget
          budget_tier             — "budget" | "midrange" | "luxury"
          duration_days           — normalised trip length
          status                  — "complete" | "partial" | "incomplete"
          missing                 — list of components that were unavailable
          warnings                — list of data quality warnings
          breakdown               — human-readable line items
    """
    warnings: list[str] = []
    missing: list[str] = []

    # --- Normalise duration ---
    days, dur_warn = _safe_int(duration_days, "duration_days")
    if dur_warn:
        warnings.append(dur_warn)
    if days <= 0:
        days = 3
        warnings.append("duration_days was 0 or invalid — defaulted to 3 days")

    budget_tier = _get_budget_tier(budget_str)

    # --- Flight cost ---
    flight_cost = 0
    flight_note = "Not included (data unavailable)"

    if flight_data is None:
        missing.append("flight")
        warnings.append("flight_data is None")
    elif not isinstance(flight_data, dict):
        missing.append("flight")
        warnings.append(f"flight_data has unexpected type: {type(flight_data)}")
    elif not flight_data.get("found", False):
        missing.append("flight")
        reason = flight_data.get("reason", "unknown reason")
        warnings.append(f"Flight not found: {reason}")
    else:
        raw_flight, fw = _safe_int(flight_data.get("roundtrip_price_inr"), "roundtrip_price_inr")
        if fw:
            warnings.append(fw)
            # Try one-way * 2 fallback
            ow, oww = _safe_int(flight_data.get("price_inr"), "price_inr")
            if oww:
                warnings.append(oww)
            raw_flight = ow * 2
        flight_cost = raw_flight
        if flight_cost > 0:
            carrier = flight_data.get("carrier", "airline")
            flight_note = f"{carrier} round-trip: Rs.{flight_cost:,}"
        else:
            missing.append("flight")
            warnings.append("Flight found but price is 0 — excluded from total")

    # --- Hotel cost ---
    hotel_cost = 0
    hotel_note = "Not included (data unavailable)"

    if hotel_data is None:
        missing.append("hotel")
        warnings.append("hotel_data is None")
    elif not isinstance(hotel_data, dict):
        missing.append("hotel")
        warnings.append(f"hotel_data has unexpected type: {type(hotel_data)}")
    else:
        raw_hotel, hw = _safe_int(
            hotel_data.get("total_hotel_estimate_inr"),
            "total_hotel_estimate_inr",
        )
        if hw:
            warnings.append(hw)
            # Fallback: nightly * days
            nightly, nw = _safe_int(hotel_data.get("cheapest_nightly_inr"), "cheapest_nightly_inr")
            if nw:
                warnings.append(nw)
            raw_hotel = nightly * days

        hotel_cost = raw_hotel
        if hotel_cost > 0:
            nightly_display = hotel_data.get("cheapest_nightly_inr", hotel_cost // days)
            hotel_note = f"Rs.{nightly_display:,}/night x {days} nights = Rs.{hotel_cost:,}"
            if not hotel_data.get("found", True):
                hotel_note += " (estimated — no direct hotel data for this city)"
        else:
            # Use tier-based estimate if hotel data is zero/missing
            estimated_nightly = _DAILY_SPEND.get(budget_tier, 3000)
            hotel_cost = estimated_nightly * days
            hotel_note = f"Estimated Rs.{estimated_nightly:,}/night x {days} nights = Rs.{hotel_cost:,} (tier estimate)"
            warnings.append(f"Hotel cost was 0 — applied {budget_tier} tier estimate")
            if "hotel" not in missing:
                missing.append("hotel (estimated)")

    # --- Daily spend ---
    daily_per_day = _DAILY_SPEND.get(budget_tier, 2500)
    daily_total = daily_per_day * days
    daily_note = f"Rs.{daily_per_day:,}/day x {days} days = Rs.{daily_total:,} (meals, transport, activities)"

    # --- Grand total ---
    grand_total = flight_cost + hotel_cost + daily_total

    # --- Status ---
    if not missing:
        status = "complete"
    elif len(missing) == 1:
        status = "partial"
    else:
        status = "incomplete"

    return {
        "flight_cost_inr": flight_cost,
        "hotel_cost_inr": hotel_cost,
        "daily_spend_inr": daily_total,
        "grand_total_inr": grand_total,
        "daily_spend_per_day_inr": daily_per_day,
        "budget_tier": budget_tier,
        "duration_days": days,
        "status": status,
        "missing": missing,
        "warnings": warnings,
        "breakdown": {
            "flights": flight_note,
            "accommodation": hotel_note,
            "daily_expenses": daily_note,
            "total": f"Rs.{grand_total:,} total estimated budget for {days}-day trip",
        },
    }
