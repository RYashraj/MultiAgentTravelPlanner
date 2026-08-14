"""
TransportAgent: Provides destination-aware local mobility guidance.

Features:
  - Airport/station transfers, metro, bus, taxi/rideshare options, and walkability.
  - Approximate travel times, station/route guidance, and estimated pricing in INR.
  - Respects trip duration, budget tier, and traveller preferences.
  - Never claims live timetables, real-time booking, or live availability.
  - Primary: Gemini AI research; Fallback: MOCK_PLACES_DB + heuristic transport engine.
"""
from __future__ import annotations

import logging
import json
from typing import Any

from app.tools.places_tool import get_transport_info

logger = logging.getLogger(__name__)

_DAILY_TRANSIT_ESTIMATE: dict[str, int] = {
    "budget": 250,
    "midrange": 600,
    "luxury": 2000,
}


def _get_budget_tier(budget: str | None) -> str:
    b = (budget or "").lower()
    if any(w in b for w in ["luxury", "no limit", "unlimited", "5 star", "five star", "premium"]):
        return "luxury"
    if any(w in b for w in ["budget", "cheap", "low", "backpack", "hostel", "friendly"]):
        return "budget"
    return "midrange"


def _call_gemini_for_transport(
    destination: str,
    origin: str | None,
    budget_tier: str,
    budget: str | None,
    duration_days: int,
    preferences: list[str] | None = None,
) -> dict[str, Any] | None:
    """Uses Gemini AI to generate structured local transport options."""
    try:
        from app.agents.gemini_client import call_gemini
        from langchain_core.messages import HumanMessage, SystemMessage

        prefs_str = ", ".join(preferences or []) or "general sightseeing"

        messages = [
            SystemMessage(content=(
                "You are TransportAgent for VoyagerAI travel planner. "
                "Provide honest, local mobility guidance for a destination. "
                "Respond ONLY with a valid JSON object (no markdown formatting, no code blocks) containing:\n"
                "- summary: string (overview of transit options and walkability)\n"
                "- airport_transfer: string (how to get from airport/station to city center with cost/time)\n"
                "- local_transit: array of strings (metro, bus, taxi, auto-rickshaw, or walking advice)\n"
                "- walkability_rating: string ('High', 'Moderate', 'Low')\n"
                "- estimated_daily_cost_inr: integer (estimated daily local transit cost per person in INR)\n"
                "- notes: string (practical transit tips, pass recommendations, or apps to download)\n\n"
                "CRITICAL RULES:\n"
                "1. Strictly honest — state costs/times as ESTIMATES, never claim live timetables or instant booking.\n"
                "2. Provide costs in INR.\n"
                "3. Match the budget tier (e.g. Metro/Bus for budget; Taxi/Rideshare for luxury)."
            )),
            HumanMessage(content=(
                f"Destination: {destination}\n"
                f"Origin: {origin or 'unspecified'}\n"
                f"Budget Tier: {budget_tier.upper()}\n"
                f"Budget: {budget or 'moderate'}\n"
                f"Duration: {duration_days} days\n"
                f"Preferences: {prefs_str}"
            )),
        ]

        raw = call_gemini(messages, timeout=15)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(l for l in lines if not l.startswith("```")).strip()

        parsed = json.loads(cleaned)
        daily_cost = int(float(str(parsed.get("estimated_daily_cost_inr", 0))))
        if daily_cost <= 0:
            daily_cost = _DAILY_TRANSIT_ESTIMATE.get(budget_tier, 500)

        return {
            "summary": str(parsed.get("summary", f"Local transit in {destination}.")),
            "airport_transfer": str(parsed.get("airport_transfer", f"Airport express bus or taxi to {destination} city center.")),
            "local_transit": [str(x) for x in parsed.get("local_transit", [])] or [f"Metro & city bus in {destination}"],
            "walkability_rating": str(parsed.get("walkability_rating", "Moderate")),
            "estimated_daily_cost_inr": daily_cost,
            "notes": str(parsed.get("notes", "Use local transit apps for route planning.")),
            "source": "ai",
        }
    except Exception as exc:
        logger.warning("TransportAgent: Gemini call failed (%s) — falling back to local heuristic", exc)
        return None


def get_transport_options(
    destination: str,
    origin: str | None = None,
    budget: str | None = None,
    duration_days: int = 3,
    preferences: list[str] | None = None,
) -> dict[str, Any]:
    """
    Public entry point for TransportAgent.
    Returns structured mobility advice. Never raises exceptions.
    """
    if not destination or not destination.strip():
        return {
            "found": False,
            "destination": None,
            "origin": origin,
            "reason": "Destination not specified.",
            "summary": "Destination missing.",
            "source": "none",
        }

    budget_tier = _get_budget_tier(budget)
    duration_days = max(duration_days or 1, 1)

    # 1. Try Gemini AI research
    ai_result = _call_gemini_for_transport(destination, origin, budget_tier, budget, duration_days, preferences)
    if ai_result:
        daily_cost = ai_result["estimated_daily_cost_inr"]
        return {
            "found": True,
            "destination": destination,
            "origin": origin,
            "budget_tier": budget_tier,
            "summary": ai_result["summary"],
            "airport_transfer": ai_result["airport_transfer"],
            "local_transit": ai_result["local_transit"],
            "walkability_rating": ai_result["walkability_rating"],
            "estimated_daily_cost_inr": daily_cost,
            "total_transport_estimate_inr": daily_cost * duration_days,
            "notes": ai_result["notes"],
            "source": "ai",
        }

    # 2. Local Fallback (Heuristic & Local DB)
    raw_info = get_transport_info(origin or "", destination)
    daily_cost = _DAILY_TRANSIT_ESTIMATE.get(budget_tier, 400)
    total_cost = daily_cost * duration_days

    fallback_summary = (
        f"Local transit in {destination}: Convenient options available including metro lines, local buses, "
        f"auto-rickshaws, and rideshare cabs (Uber/Ola). Walkability in central areas is high."
    )
    airport_transfer = f"Taxi or airport shuttle bus to central {destination}: ~30–60 mins (Est. Rs.300–800)."
    local_transit = [
        f"🚇 Metro / Rail: Fastest option for city travel (~Rs.20–60/trip)",
        f"🚕 Taxi / Rideshare: Uber/Ola available for point-to-point travel (~Rs.150–400/trip)",
        f"🚶 Walking: Central tourist districts are easily walkable"
    ]

    return {
        "found": True,
        "destination": destination,
        "origin": origin,
        "budget_tier": budget_tier,
        "summary": fallback_summary,
        "airport_transfer": airport_transfer,
        "local_transit": local_transit,
        "walkability_rating": "Moderate to High",
        "estimated_daily_cost_inr": daily_cost,
        "total_transport_estimate_inr": total_cost,
        "notes": f"Intercity transport note:\n{raw_info[:300]}" if raw_info else "Check local transit apps upon arrival.",
        "source": "local_db",
    }
