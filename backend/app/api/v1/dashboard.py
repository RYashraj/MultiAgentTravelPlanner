"""
Dashboard API endpoint.

Returns a single aggregated response for the trip dashboard page.
Each section (flights, hotels, weather, attractions, budget) is fetched
independently and fails gracefully — one broken section does not crash
the whole response. The frontend renders each section based on its own
`status` field.
"""
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agents.budget_agent import compute_budget
from app.agents.flight_agent import get_flight_options
from app.agents.hotel_agent import get_hotel_options
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.repositories import ItineraryRepository, TripRepository
from app.tools.places_tool import MOCK_PLACES_DB, search_places
from app.tools.weather_tool import get_weather

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trips", tags=["dashboard"])


@router.get("/{trip_id}/dashboard")
def get_dashboard(
    trip_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Aggregate all agent data for the trip dashboard.

    Returns independent sections: overview, itinerary, flights, hotels,
    weather, attractions, budget. Each section has a `status` field:
    "ok" | "partial" | "unavailable". One section failing does NOT affect others.
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

    # ----------------------------------------------------------------
    # Section: Itinerary
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
    # Section: Flights — best-effort, needs origin from itinerary context
    # We extract origin from the itinerary content heuristically, or mark unavailable.
    # ----------------------------------------------------------------
    try:
        # Try to get origin from trip messages (last user message with "from")
        from app.repositories import MessageRepository
        import re
        messages = MessageRepository(db).list_for_trip(trip_id)
        origin = None
        for msg in messages:
            if msg.role == "user":
                m = re.search(r"\bfrom\s+([A-Za-z][A-Za-z\s]{1,25}?)(?:\s+to\b|\s+for\b|,|\.|\s+with\b|$)", msg.content, re.IGNORECASE)
                if m:
                    candidate = m.group(1).strip().title()
                    if candidate.lower() not in ("here", "home", "there", "the", "a"):
                        origin = candidate
                        break

        flight_data = get_flight_options(origin, destination, 3)
        if flight_data.get("found"):
            result["flights"] = {
                "status": "ok",
                "data": flight_data,
            }
        else:
            result["flights"] = {
                "status": "partial",
                "data": flight_data,
                "message": flight_data.get("reason", "Flight data unavailable"),
            }
    except Exception as exc:
        logger.warning("Dashboard: flights section failed for trip %s: %s", trip_id, exc)
        result["flights"] = {
            "status": "unavailable",
            "data": None,
            "message": "Could not load flight information.",
        }

    # ----------------------------------------------------------------
    # Section: Hotels
    # ----------------------------------------------------------------
    try:
        # Extract duration and budget from messages
        duration_days = 3
        budget_str = None
        messages = MessageRepository(db).list_for_trip(trip_id)
        for msg in messages:
            if msg.role == "user":
                dm = re.search(r"(\d+)\s*(?:day|days|night|nights)", msg.content, re.IGNORECASE)
                if dm:
                    duration_days = int(dm.group(1))
                bm = re.search(r"(?:budget|rs\.?|inr|usd|\$)\s*[\d,]+", msg.content, re.IGNORECASE)
                if bm and not budget_str:
                    budget_str = bm.group(0)

        hotel_data = get_hotel_options(destination, budget_str, duration_days)
        if hotel_data.get("found"):
            result["hotels"] = {"status": "ok", "data": hotel_data}
        else:
            result["hotels"] = {
                "status": "partial",
                "data": hotel_data,
                "message": hotel_data.get("reason", "Hotel data unavailable"),
            }
    except Exception as exc:
        logger.warning("Dashboard: hotels section failed for trip %s: %s", trip_id, exc)
        result["hotels"] = {
            "status": "unavailable",
            "data": None,
            "message": "Could not load hotel information.",
        }

    # ----------------------------------------------------------------
    # Section: Weather
    # ----------------------------------------------------------------
    try:
        weather_raw = get_weather.invoke({"location": destination})
        weather_data = json.loads(weather_raw) if isinstance(weather_raw, str) else weather_raw
        result["weather"] = {"status": "ok", "data": weather_data}
    except Exception as exc:
        logger.warning("Dashboard: weather section failed for trip %s: %s", trip_id, exc)
        result["weather"] = {"status": "unavailable", "data": None, "message": "Could not load weather data."}

    # ----------------------------------------------------------------
    # Section: Attractions
    # ----------------------------------------------------------------
    try:
        attractions_raw = search_places.invoke({"location": destination, "query_type": "attraction"})
        attractions = json.loads(attractions_raw) if isinstance(attractions_raw, str) else attractions_raw
        if isinstance(attractions, list) and attractions:
            result["attractions"] = {"status": "ok", "data": attractions[:8]}
        else:
            result["attractions"] = {"status": "unavailable", "data": [], "message": "No attractions found."}
    except Exception as exc:
        logger.warning("Dashboard: attractions section failed for trip %s: %s", trip_id, exc)
        result["attractions"] = {"status": "unavailable", "data": [], "message": "Could not load attractions."}

    # ----------------------------------------------------------------
    # Section: Budget
    # ----------------------------------------------------------------
    try:
        flight_d = result.get("flights", {}).get("data")
        hotel_d = result.get("hotels", {}).get("data")
        budget_breakdown = compute_budget(flight_d, hotel_d, duration_days, budget_str)
        result["budget"] = {"status": "ok", "data": budget_breakdown}
        if budget_breakdown.get("status") in ("partial", "incomplete"):
            result["budget"]["status"] = budget_breakdown["status"]
    except Exception as exc:
        logger.warning("Dashboard: budget section failed for trip %s: %s", trip_id, exc)
        result["budget"] = {
            "status": "unavailable",
            "data": None,
            "message": "Could not compute budget breakdown.",
        }

    return result
