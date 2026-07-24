"""Attraction Agent for Travel Planner."""
import logging
from typing import Any

from app.agents.state import AgentState
from app.tools.places_tool import search_attractions

logger = logging.getLogger(__name__)


def attraction_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node function for searching attractions."""
    destination = state.get("destination", "")
    preferences = state.get("preferences", [])

    try:
        raw_items = search_attractions(destination, preferences)
        items: list[dict[str, Any]] = []
        for raw in raw_items:
            category = str(raw.get("category", "General"))
            outdoor = bool(raw.get("outdoor", category.lower() in ["nature", "park", "outdoor", "sightseeing"]))
            rating = raw.get("rating")
            if rating is not None:
                rating = float(rating)

            items.append({
                "name": str(raw.get("name", "Unknown Attraction")),
                "category": category,
                "outdoor": outdoor,
                "rating": rating,
            })

        summary = f"Found {len(items)} attraction(s) in {destination}."
        attraction_output = {
            "items": items,
            "summary": summary,
        }
    except Exception as exc:
        logger.error("Error searching attractions for destination '%s': %s", destination, exc, exc_info=True)
        attraction_output = {
            "items": [],
            "summary": f"Unable to fetch attractions for {destination}.",
        }

    existing_outputs = dict(state.get("agent_outputs") or {})
    return {"agent_outputs": {**existing_outputs, "attractions": attraction_output}}
