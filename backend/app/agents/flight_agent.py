"""
FlightAgent: returns structured flight options for a given origin/destination pair.

Design decisions:
  - No live Amadeus call here — Amadeus sandbox is sparse for many routes (roadmap
    explicitly flags this). See amadeus_tool.py for the best-effort real API wrapper.
  - Uses an internal flight route table for demo reliability.
  - Returns a typed dict so BudgetAgent and PlannerAgent can consume it safely.
  - Every failure path returns found=False with a human-readable reason, never raises.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Flight route database (demo-reliable cities)
# ---------------------------------------------------------------------------

_FLIGHT_DB: dict[tuple[str, str], dict[str, Any]] = {
    # Indian domestic routes
    ("mumbai", "delhi"): {
        "carrier": "IndiGo / Air India",
        "duration_hrs": 2.0,
        "price_inr": 4500,
        "price_range_inr": "Rs.2,800-7,000",
        "flight_class": "Economy",
        "frequency": "Multiple flights daily",
    },
    ("delhi", "mumbai"): {
        "carrier": "IndiGo / Air India",
        "duration_hrs": 2.0,
        "price_inr": 4500,
        "price_range_inr": "Rs.2,800-7,000",
        "flight_class": "Economy",
        "frequency": "Multiple flights daily",
    },
    ("mumbai", "goa"): {
        "carrier": "IndiGo / SpiceJet",
        "duration_hrs": 1.0,
        "price_inr": 3200,
        "price_range_inr": "Rs.1,800-5,500",
        "flight_class": "Economy",
        "frequency": "5-8 flights daily",
    },
    ("goa", "mumbai"): {
        "carrier": "IndiGo / SpiceJet",
        "duration_hrs": 1.0,
        "price_inr": 3200,
        "price_range_inr": "Rs.1,800-5,500",
        "flight_class": "Economy",
        "frequency": "5-8 flights daily",
    },
    ("delhi", "goa"): {
        "carrier": "IndiGo / Air India",
        "duration_hrs": 2.5,
        "price_inr": 5800,
        "price_range_inr": "Rs.3,500-9,000",
        "flight_class": "Economy",
        "frequency": "3-5 flights daily",
    },
    ("goa", "delhi"): {
        "carrier": "IndiGo / Air India",
        "duration_hrs": 2.5,
        "price_inr": 5800,
        "price_range_inr": "Rs.3,500-9,000",
        "flight_class": "Economy",
        "frequency": "3-5 flights daily",
    },
    ("gujarat", "mumbai"): {
        "carrier": "IndiGo / Air India Express",
        "duration_hrs": 1.0,
        "price_inr": 2800,
        "price_range_inr": "Rs.1,500-4,500",
        "flight_class": "Economy",
        "frequency": "AMD to BOM: 6+ flights daily",
    },
    ("ahmedabad", "mumbai"): {
        "carrier": "IndiGo / Air India Express",
        "duration_hrs": 1.0,
        "price_inr": 2800,
        "price_range_inr": "Rs.1,500-4,500",
        "flight_class": "Economy",
        "frequency": "6+ flights daily",
    },
    ("ahmedabad", "delhi"): {
        "carrier": "IndiGo / Air India",
        "duration_hrs": 1.5,
        "price_inr": 3500,
        "price_range_inr": "Rs.2,000-6,000",
        "flight_class": "Economy",
        "frequency": "4-6 flights daily",
    },
    ("mumbai", "bangalore"): {
        "carrier": "IndiGo / Air India",
        "duration_hrs": 1.5,
        "price_inr": 3800,
        "price_range_inr": "Rs.2,200-6,500",
        "flight_class": "Economy",
        "frequency": "Multiple flights daily",
    },
    # International routes
    ("mumbai", "tokyo"): {
        "carrier": "Air India / Japan Airlines",
        "duration_hrs": 9.5,
        "price_inr": 55000,
        "price_range_inr": "Rs.40,000-80,000",
        "flight_class": "Economy",
        "frequency": "Daily (BOM to NRT)",
    },
    ("delhi", "tokyo"): {
        "carrier": "Air India / ANA",
        "duration_hrs": 9.0,
        "price_inr": 52000,
        "price_range_inr": "Rs.38,000-75,000",
        "flight_class": "Economy",
        "frequency": "Daily (DEL to NRT)",
    },
    ("mumbai", "london"): {
        "carrier": "Air India / British Airways",
        "duration_hrs": 9.5,
        "price_inr": 65000,
        "price_range_inr": "Rs.45,000-1,20,000",
        "flight_class": "Economy",
        "frequency": "Daily (BOM to LHR)",
    },
    ("delhi", "london"): {
        "carrier": "Air India / British Airways",
        "duration_hrs": 8.5,
        "price_inr": 62000,
        "price_range_inr": "Rs.42,000-1,10,000",
        "flight_class": "Economy",
        "frequency": "Daily (DEL to LHR)",
    },
}


def _normalise(city: str) -> str:
    """Lower-case and strip for fuzzy matching."""
    return city.strip().lower()


def _find_route(origin: str, destination: str) -> dict[str, Any] | None:
    """
    Find a matching route using exact then partial key matching.
    Returns None if no route found — never raises.
    """
    o = _normalise(origin)
    d = _normalise(destination)

    # Exact match
    if (o, d) in _FLIGHT_DB:
        return _FLIGHT_DB[(o, d)]

    # Partial match — one key contains the other
    for (ok, dk), data in _FLIGHT_DB.items():
        o_match = ok in o or o in ok
        d_match = dk in d or d in dk
        if o_match and d_match:
            return data

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_flight_options(
    origin: str | None,
    destination: str,
    duration_days: int = 3,
) -> dict[str, Any]:
    """
    Return structured flight information for a route.

    Args:
        origin:        Departure city. May be None (handled gracefully — found=False).
        destination:   Arrival city.
        duration_days: Trip length in days — used to estimate round-trip cost.

    Returns:
        Dict with keys: found, origin, destination, and when found=True:
        carrier, duration_hrs, price_inr (one-way), roundtrip_price_inr,
        price_range_inr, flight_class, frequency, notes.
        When found=False: reason, notes.
    """
    if not origin or not origin.strip():
        return {
            "found": False,
            "origin": None,
            "destination": destination,
            "reason": "Origin city not specified — cannot compute flight cost.",
            "notes": "Ask the traveller where they are departing from.",
        }

    if not destination or not destination.strip():
        return {
            "found": False,
            "origin": origin,
            "destination": None,
            "reason": "Destination not specified.",
            "notes": "",
        }

    try:
        route = _find_route(origin, destination)

        if route is None:
            # Clearly labelled non-data — not a fabricated number
            return {
                "found": False,
                "origin": origin,
                "destination": destination,
                "reason": (
                    f"No flight data for {origin} to {destination} in the demo database. "
                    "This is a known gap — not all city pairs are covered."
                ),
                "notes": (
                    "Check Google Flights, MakeMyTrip, or Skyscanner for real fares. "
                    "Typical economy estimate for Indian domestic: Rs.2,000-8,000. "
                    "International: Rs.30,000-1,20,000 depending on distance."
                ),
            }

        one_way = int(route["price_inr"])
        if one_way <= 0:
            one_way = 0

        roundtrip = one_way * 2

        return {
            "found": True,
            "origin": origin,
            "destination": destination,
            "carrier": route["carrier"],
            "duration_hrs": route["duration_hrs"],
            "price_inr": one_way,
            "roundtrip_price_inr": roundtrip,
            "price_range_inr": route["price_range_inr"],
            "flight_class": route["flight_class"],
            "frequency": route["frequency"],
            "notes": (
                f"Book 2-4 weeks ahead on MakeMyTrip or GoIbibo for best fares. "
                f"Round-trip estimate: Rs.{roundtrip:,}"
            ),
        }

    except Exception as exc:
        logger.error(
            "FlightAgent: unexpected error for %s to %s: %s",
            origin, destination, exc, exc_info=True,
        )
        return {
            "found": False,
            "origin": origin,
            "destination": destination,
            "reason": "Internal error computing flight data.",
            "notes": "Please check flight booking sites directly.",
        }
