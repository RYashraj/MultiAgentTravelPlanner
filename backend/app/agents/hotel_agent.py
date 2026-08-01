"""
HotelAgent: returns structured hotel recommendations filtered by budget tier.

Design decisions:
  - Delegates to existing get_budget_hotels() in places_tool to avoid duplication.
  - Returns structured data (not prose) so BudgetAgent can extract nightly cost.
  - Handles: no budget specified, unknown city, empty hotel list, negative prices.
  - Every failure path returns found=False with a clear reason, never raises.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from app.tools.places_tool import MOCK_PLACES_DB, get_budget_hotels

logger = logging.getLogger(__name__)

_DAILY_HOTEL_ESTIMATE: dict[str, int] = {
    "budget": 1800,
    "midrange": 4500,
    "luxury": 22000,
}


def _get_budget_tier(budget: str | None) -> str:
    b = (budget or "").lower()
    if any(w in b for w in ["luxury", "no limit", "unlimited", "5 star", "five star", "premium"]):
        return "luxury"
    if any(w in b for w in ["budget", "cheap", "low", "backpack", "hostel", "friendly"]):
        return "budget"
    return "midrange"


def _extract_nightly_price(hotel: dict[str, Any]) -> int | None:
    """Parse the first plausible nightly price from a hotel description string."""
    desc = hotel.get("description", "")
    stripped = desc.replace(",", "")
    matches = re.findall(r"\d+", stripped)
    for m in matches:
        try:
            val = int(m)
            if 300 <= val <= 200_000:
                return val
        except ValueError:
            continue
    return None


def get_hotel_options(
    destination: str,
    budget: str | None,
    duration_days: int = 3,
) -> dict[str, Any]:
    """
    Return structured hotel recommendations for the destination and budget.

    Args:
        destination:   City to search hotels in.
        budget:        Raw budget string from user (e.g., "Rs.50,000", "budget", "luxury").
        duration_days: Trip length used to compute total hotel cost estimate.

    Returns:
        Dict with: found, destination, budget_tier, hotels list, cheapest_nightly_inr,
        total_hotel_estimate_inr, notes. When found=False: reason field added.
    """
    if not destination or not destination.strip():
        return {
            "found": False,
            "destination": None,
            "budget_tier": "midrange",
            "hotels": [],
            "reason": "Destination not specified.",
            "cheapest_nightly_inr": 0,
            "total_hotel_estimate_inr": 0,
            "notes": "",
        }

    budget_tier = _get_budget_tier(budget)
    duration_days = max(duration_days or 1, 1)

    try:
        loc_key = next(
            (k for k in MOCK_PLACES_DB
             if k.lower() in destination.lower() or destination.lower() in k.lower()),
            None,
        )
        all_places = MOCK_PLACES_DB.get(loc_key, []) if loc_key else []
        hotels = get_budget_hotels(all_places, budget)

        if not hotels:
            daily_estimate = _DAILY_HOTEL_ESTIMATE.get(budget_tier, 3000)
            total_estimate = daily_estimate * duration_days
            return {
                "found": False,
                "destination": destination,
                "budget_tier": budget_tier,
                "hotels": [],
                "reason": (
                    f"No hotel data for {destination} in demo database "
                    f"({budget_tier} tier). Known coverage gap."
                ),
                "cheapest_nightly_inr": daily_estimate,
                "total_hotel_estimate_inr": total_estimate,
                "notes": (
                    f"Estimated {budget_tier} hotel in {destination}: ~Rs.{daily_estimate:,}/night. "
                    f"Check Booking.com or MakeMyTrip for live availability."
                ),
            }

        prices = [_extract_nightly_price(h) for h in hotels]
        valid_prices = [p for p in prices if p is not None and p > 0]
        cheapest = min(valid_prices) if valid_prices else _DAILY_HOTEL_ESTIMATE.get(budget_tier, 3000)
        total_estimate = cheapest * duration_days

        return {
            "found": True,
            "destination": destination,
            "budget_tier": budget_tier,
            "hotels": hotels,
            "cheapest_nightly_inr": cheapest,
            "total_hotel_estimate_inr": total_estimate,
            "notes": (
                f"Showing {budget_tier} hotels in {destination}. "
                f"Cheapest from Rs.{cheapest:,}/night. "
                f"Estimated {duration_days}-night cost: Rs.{total_estimate:,}."
            ),
        }

    except Exception as exc:
        logger.error("HotelAgent error for %s: %s", destination, exc, exc_info=True)
        daily_estimate = _DAILY_HOTEL_ESTIMATE.get(budget_tier, 3000)
        return {
            "found": False,
            "destination": destination,
            "budget_tier": budget_tier,
            "hotels": [],
            "reason": "Internal error fetching hotel data.",
            "cheapest_nightly_inr": daily_estimate,
            "total_hotel_estimate_inr": daily_estimate * duration_days,
            "notes": "Please check hotel booking sites directly.",
        }
