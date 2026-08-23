"""
FoodAgent: Provides destination-focused culinary and dining recommendations.

Features:
  - Local specialties, must-try dishes, iconic restaurants, street food hubs, and dietary options.
  - Estimated per-meal and daily dining budgets in INR tailored to budget tier.
  - Respects dietary preferences (Vegetarian, Vegan, Jain, Halal, Gluten-Free).
  - Never claims live table reservations or real-time menu availability.
  - Primary: Gemini AI research; Fallback: MOCK_PLACES_DB + local food engine.
"""
from __future__ import annotations

import logging
import json
from typing import Any

from app.tools.places_tool import MOCK_PLACES_DB

logger = logging.getLogger(__name__)

_DAILY_DINING_ESTIMATE: dict[str, int] = {
    "budget": 400,
    "midrange": 1200,
    "luxury": 3500,
}


def _get_budget_tier(budget: str | None) -> str:
    b = (budget or "").lower()
    if any(w in b for w in ["luxury", "no limit", "unlimited", "5 star", "five star", "fine dining"]):
        return "luxury"
    if any(w in b for w in ["budget", "cheap", "low", "street food", "dhabas"]):
        return "budget"
    return "midrange"


def _call_gemini_for_food(
    destination: str,
    budget_tier: str,
    budget: str | None,
    duration_days: int,
    dietary_preferences: list[str] | None = None,
) -> dict[str, Any] | None:
    """Uses Gemini AI to generate structured dining recommendations."""
    try:
        from app.agents.gemini_client import call_gemini
        from langchain_core.messages import HumanMessage, SystemMessage

        diet_str = ", ".join(dietary_preferences or []) or "no special restrictions"

        messages = [
            SystemMessage(content=(
                "You are FoodAgent for VoyagerAI travel planner. "
                "Provide authentic culinary and restaurant recommendations for a destination. "
                "Respond ONLY with a valid JSON object (no markdown formatting, no code blocks) containing:\n"
                "- summary: string (overview of local food culture & food scene)\n"
                "- must_try_dishes: array of strings (top 3–5 famous dishes/beverages)\n"
                "- recommended_places: array of objects with keys: name (string), type ('restaurant'|'street_food'|'cafe'), description (string), estimated_cost_inr (integer per meal), rating (float 1-5 optional)\n"
                "- street_food_hubs: array of strings (popular food streets or night markets)\n"
                "- estimated_daily_food_cost_inr: integer (estimated total dining cost per person per day in INR)\n"
                "- dietary_notes: string (guidance for dietary restrictions if requested)\n\n"
                "CRITICAL RULES:\n"
                "1. Strictly honest — state costs as ESTIMATES, never claim live table bookings.\n"
                "2. Provide costs in INR.\n"
                "3. Match the budget tier and dietary restrictions requested."
            )),
            HumanMessage(content=(
                f"Destination: {destination}\n"
                f"Budget Tier: {budget_tier.upper()}\n"
                f"Budget: {budget or 'moderate'}\n"
                f"Duration: {duration_days} days\n"
                f"Dietary Restrictions/Preferences: {diet_str}"
            )),
        ]

        raw = call_gemini(messages, timeout=15)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(l for l in lines if not l.startswith("```")).strip()

        parsed = json.loads(cleaned)
        daily_cost = int(float(str(parsed.get("estimated_daily_food_cost_inr", 0))))
        if daily_cost <= 0:
            daily_cost = _DAILY_DINING_ESTIMATE.get(budget_tier, 1000)

        places = []
        for p in parsed.get("recommended_places", []):
            if isinstance(p, dict) and p.get("name"):
                places.append({
                    "name": str(p["name"]),
                    "type": str(p.get("type", "restaurant")),
                    "description": str(p.get("description", "Popular local eatery.")),
                    "estimated_cost_inr": int(float(str(p.get("estimated_cost_inr", 300)))),
                    "rating": float(p["rating"]) if p.get("rating") else 4.5,
                })

        return {
            "summary": str(parsed.get("summary", f"Culinary scene in {destination}.")),
            "must_try_dishes": [str(x) for x in parsed.get("must_try_dishes", [])] or [f"Local {destination} Thali"],
            "recommended_places": places,
            "street_food_hubs": [str(x) for x in parsed.get("street_food_hubs", [])],
            "estimated_daily_food_cost_inr": daily_cost,
            "dietary_notes": str(parsed.get("dietary_notes", f"Dietary preferences: {diet_str}")),
            "source": "ai",
        }
    except Exception as exc:
        logger.warning("FoodAgent: Gemini call failed (%s) — falling back to local heuristic", exc)
        return None


def get_food_recommendations(
    destination: str,
    budget: str | None = None,
    duration_days: int = 3,
    dietary_preferences: list[str] | None = None,
) -> dict[str, Any]:
    """
    Public entry point for FoodAgent.
    Returns structured culinary recommendations. Never raises exceptions.
    """
    if not destination or not destination.strip():
        return {
            "found": False,
            "destination": None,
            "reason": "Destination not specified.",
            "summary": "Destination missing.",
            "source": "none",
        }

    budget_tier = _get_budget_tier(budget)
    duration_days = max(duration_days or 1, 1)

    # 1. Try Gemini AI research
    ai_result = _call_gemini_for_food(destination, budget_tier, budget, duration_days, dietary_preferences)
    if ai_result:
        daily_cost = ai_result["estimated_daily_food_cost_inr"]
        return {
            "found": True,
            "destination": destination,
            "budget_tier": budget_tier,
            "summary": ai_result["summary"],
            "must_try_dishes": ai_result["must_try_dishes"],
            "recommended_places": ai_result["recommended_places"],
            "street_food_hubs": ai_result["street_food_hubs"],
            "estimated_daily_food_cost_inr": daily_cost,
            "total_food_estimate_inr": daily_cost * duration_days,
            "dietary_notes": ai_result["dietary_notes"],
            "source": "ai",
        }

    # 2. Local Fallback (Places Tool + Local Heuristics)
    loc_key = next(
        (k for k in MOCK_PLACES_DB.keys() if k.lower() in destination.lower() or destination.lower() in k.lower()),
        None,
    )
    mock_places = [p for p in MOCK_PLACES_DB.get(loc_key, []) if p.get("type") in ("restaurant", "food")] if loc_key else []
    daily_cost = _DAILY_DINING_ESTIMATE.get(budget_tier, 800)
    total_cost = daily_cost * duration_days

    recommended_places = []
    for p in mock_places:
        recommended_places.append({
            "name": p.get("name", "Local Restaurant"),
            "type": "restaurant",
            "description": p.get("description", "Authentic regional cuisine."),
            "estimated_cost_inr": int(daily_cost / 3),
            "rating": p.get("rating", 4.3),
        })

    if not recommended_places:
        recommended_places = [
            {
                "name": f"Central {destination} Food Street",
                "type": "street_food",
                "description": "Bustling food street featuring iconic regional snacks & sweets.",
                "estimated_cost_inr": 200,
                "rating": 4.5,
            },
            {
                "name": f"Royal {destination} Dining Hall",
                "type": "restaurant",
                "description": "Traditional thali and local regional delicacies.",
                "estimated_cost_inr": 500,
                "rating": 4.6,
            },
        ]

    return {
        "found": True,
        "destination": destination,
        "budget_tier": budget_tier,
        "summary": f"Discover authentic local flavors, street food, and traditional dining in {destination}.",
        "must_try_dishes": [f"Regional {destination} Specialty Thali", "Local Street Snacks", "Artisanal Beverages"],
        "recommended_places": recommended_places,
        "street_food_hubs": [f"Main Market Food Lane, {destination}", "Night Bazaar Street Food Zone"],
        "estimated_daily_food_cost_inr": daily_cost,
        "total_food_estimate_inr": total_cost,
        "dietary_notes": f"Dietary options ({', '.join(dietary_preferences or ['Standard'])}) widely available upon request.",
        "source": "local_db",
    }
