"""Pydantic request and response models for the API."""
from app.schemas.bookings import BudgetBreakdown, FlightOption, HotelOption
from app.schemas.trips import (
    ChatResponse,
    ItineraryResponse,
    MessageCreate,
    MessageResponse,
    TripCreate,
    TripResponse,
)

__all__ = [
    "FlightOption",
    "HotelOption",
    "BudgetBreakdown",
    "TripCreate",
    "TripResponse",
    "MessageCreate",
    "MessageResponse",
    "ChatResponse",
    "ItineraryResponse",
]
