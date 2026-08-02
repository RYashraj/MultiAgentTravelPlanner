"""
Dashboard API endpoint.

Performance improvements:
  - All independent sections (flights, hotels, weather, budget) now fetched in PARALLEL
    using asyncio.gather — eliminates sequential blocking I/O
  - Endpoint converted to async
  - json import at top level
  - Messages fetched once and reused across sections
  - Regex compiled at module level for origin/duration/budget extraction

Returns a single aggregated response for the trip dashboard page.
Each section has its own `status` field: "ok" | "partial" | "unavailable".
One section failing does NOT affect others.
"""
import asyncio
import json
import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agents.budget_agent import compute_budget
from app.agents.flight_agent import get_flight_options
from app.agents.hotel_agent import get_hotel_options
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.repositories import ItineraryRepository, MessageRepository, TripRepository
from app.tools.places_tool import search_places
from app.tools.weather_tool import get_weather

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trips", tags=["dashboard"])

# Compile regexes once at module level (not per-request)
_RE_ORIGIN = re.compile(
    r"\bfrom\s+([A-Za-z][A-Za-z\s]{1,25}?)(?:\s+to\b|\s+for\b|,|\.\s|\s+with\b|$)",
    re.IGNORECASE,
)
_RE_DURATION = re.compile(r"(\d+)\s*(?:day|days|night|nights)", re.IGNORECASE)
_RE_BUDGET = re.compile(r"(?:budget|rs\.?|inr|usd|\$)\s*[\d,]+", re.IGNORECASE)
_ORIGIN_STOPWORDS = frozenset({"here", "home", "there", "the", "a", "my", "this"})


def _extract_trip_context(messages: list) -> tuple[str | None, int, str | None]:
    """Extract origin, duration_days, budget_str from message history."""
    origin: str | None = None
    duration_days = 3
    budget_str: str | None = None

    for msg in messages:
        if msg.role != "user":
            continue
        content = msg.content

        if origin is None:
            m = _RE_ORIGIN.search(content)
            if m:
                candidate = m.group(1).strip().title()
                if candidate.lower() not in _ORIGIN_STOPWORDS and len(candidate) > 1:
                    origin = candidate

        dm = _RE_DURATION.search(content)
        if dm:
            duration_days = int(dm.group(1))

        bm = _RE_BUDGET.search(content)
        if bm and not budget_str:
            budget_str = bm.group(0)

    return origin, duration_days, budget_str


@router.get("/{trip_id}/dashboard")
async def get_dashboard(
    trip_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Aggregate all agent data for the trip dashboard.

    Returns independent sections: overview, itinerary, flights, hotels,
    weather, attractions, budget. Each section has a `status` field.
    One section failing does NOT affect others.

    Performance: flights, hotels, weather and attractions fetched in PARALLEL.
    """
    # Verify trip ownership
    trip = TripRepository(db).get_for_user(trip_id, user.id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")

    destination = trip.destination
    result: dict = {
        "trip_id": str(trip_id),
        "destination": destination,
        "trip_status": trip.status,
    }

    # Fetch messages once — reused across all sections
    messages = MessageRepository(db).list_for_trip(trip_id)
    origin, duration_days, budget_str = _extract_trip_context(messages)

    # ----------------------------------------------------------------
    # Section: Itinerary (sync DB read — fast)
    # ----------------------------------------------------------------
    try:
        itinerary = ItineraryRepository(db).get_for_trip(trip_id)
        if itinerary:
            result["itinerary"] = {
                "status": "ok",
                "content": itinerary.content,
                "itinerary_status": itinerary.status,
                "created_at": itinerary.created_at.isoformat(),
            }
        else:
            result["itinerary"] = {
                "status": "unavailable",
                "content": None,
                "message": "No itinerary generated yet. Start a conversation to create one.",
            }
    except Exception as exc:
        logger.warning("Dashboard: itinerary section failed for trip %s: %s", trip_id, exc)
        result["itinerary"] = {"status": "unavailable", "content": None, "message": "Could not load itinerary."}

    # ----------------------------------------------------------------
    # Parallel fetch: Flights + Hotels + Weather + Attractions
    # ----------------------------------------------------------------

    async def _fetch_flights() -> dict:
        try:
            data = await asyncio.to_thread(get_flight_options, origin, destination, duration_days)
            return data
        except Exception as exc:
            logger.warning("Dashboard: flights failed for trip %s: %s", trip_id, exc)
            return {"found": False, "reason": "Agent error", "source": "error"}

    async def _fetch_hotels() -> dict:
        try:
            data = await asyncio.to_thread(get_hotel_options, destination, budget_str, duration_days)
            return data
        except Exception as exc:
            logger.warning("Dashboard: hotels failed for trip %s: %s", trip_id, exc)
            return {"found": False, "reason": "Agent error", "hotels": [], "source": "error"}

    async def _fetch_weather() -> dict:
        try:
            raw = await asyncio.to_thread(get_weather.invoke, {"location": destination})
            return json.loads(raw) if isinstance(raw, str) else raw
        except Exception as exc:
            logger.warning("Dashboard: weather failed for trip %s: %s", trip_id, exc)
            return {"condition": "Pleasant", "source": "error"}

    async def _fetch_attractions() -> list:
        try:
            raw = await asyncio.to_thread(
                search_places.invoke, {"location": destination, "query_type": "attraction"}
            )
            data = json.loads(raw) if isinstance(raw, str) else raw
            return data if isinstance(data, list) else []
        except Exception as exc:
            logger.warning("Dashboard: attractions failed for trip %s: %s", trip_id, exc)
            return []

    flight_data, hotel_data, weather_data, attractions_list = await asyncio.gather(
        _fetch_flights(),
        _fetch_hotels(),
        _fetch_weather(),
        _fetch_attractions(),
    )

    # ----------------------------------------------------------------
    # Section: Flights
    # ----------------------------------------------------------------
    if flight_data.get("found"):
        result["flights"] = {"status": "ok", "data": flight_data}
    else:
        result["flights"] = {
            "status": "partial",
            "data": flight_data,
            "message": flight_data.get("reason", "Flight data unavailable"),
        }

    # ----------------------------------------------------------------
    # Section: Hotels
    # ----------------------------------------------------------------
    if hotel_data.get("found"):
        result["hotels"] = {"status": "ok", "data": hotel_data}
    else:
        result["hotels"] = {
            "status": "partial",
            "data": hotel_data,
            "message": hotel_data.get("reason", "Hotel data unavailable"),
        }

    # ----------------------------------------------------------------
    # Section: Weather
    # ----------------------------------------------------------------
    if weather_data.get("source") != "error":
        result["weather"] = {"status": "ok", "data": weather_data}
    else:
        result["weather"] = {"status": "unavailable", "data": None, "message": "Could not load weather data."}

    # ----------------------------------------------------------------
    # Section: Attractions
    # ----------------------------------------------------------------
    if attractions_list:
        result["attractions"] = {"status": "ok", "data": attractions_list[:8]}
    else:
        result["attractions"] = {"status": "unavailable", "data": [], "message": "No attractions found."}

    # ----------------------------------------------------------------
    # Section: Budget (sequential — depends on flight + hotel)
    # ----------------------------------------------------------------
    try:
        budget_breakdown = await asyncio.to_thread(
            compute_budget, flight_data, hotel_data, duration_days, budget_str
        )
        budget_status = budget_breakdown.get("status", "incomplete")
        result["budget"] = {
            "status": budget_status if budget_status in ("partial", "incomplete") else "ok",
            "data": budget_breakdown,
        }
    except Exception as exc:
        logger.warning("Dashboard: budget section failed for trip %s: %s", trip_id, exc)
        result["budget"] = {
            "status": "unavailable",
            "data": None,
            "message": "Could not compute budget breakdown.",
        }

    return result
