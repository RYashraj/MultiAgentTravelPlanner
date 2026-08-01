"""
Pydantic schemas for Flight, Hotel, and Budget options in VoyagerAI.
"""
import re
from pydantic import BaseModel, Field


def parse_price_to_number(price_str: str | None) -> float | None:
    """Helper function to extract a numeric float value from a formatted price string (e.g., '₹4,200' -> 4200.0 or '€180' -> 180.0)."""
    if not price_str:
        return None
    cleaned = re.sub(r"[^\d.]", "", price_str.replace(",", ""))
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None



class FlightOption(BaseModel):
    carrier: str = Field(description="Airline name or carrier code")
    flight_number: str = Field(description="Flight code e.g. 6E-2035")
    departure_time: str = Field(description="Departure time HH:MM")
    arrival_time: str = Field(description="Arrival time HH:MM")
    price: str = Field(description="Formatted price string e.g. ₹4,200")
    duration: str = Field(description="Flight duration e.g. 2h 15m")
    cabin: str = Field(default="Economy", description="Cabin class")
    price_inr: float | None = Field(default=None, description="Numeric fare for budget calculation")


class HotelOption(BaseModel):
    name: str = Field(description="Hotel or hostel name")
    price_per_night: str = Field(description="Nightly rate string e.g. ₹3,800")
    currency: str = Field(default="INR", description="Currency code")
    room_type: str = Field(description="Room category e.g. Standard Room")
    description: str = Field(description="Short description and amenities")
    price_inr: float | None = Field(default=None, description="Numeric nightly price for budget calculation")


class BudgetBreakdown(BaseModel):
    user_budget_str: str = Field(description="Raw user budget string")
    user_budget_inr: float | None = Field(default=None, description="Parsed numeric budget")
    subtotal: float = Field(default=0.0, description="Subtotal cost before taxes or buffers")
    estimated_total_inr: float = Field(description="Estimated total trip cost")
    flight_round_trip: float = Field(default=0.0, description="Round trip flight estimate")
    hotel_total: float = Field(default=0.0, description="Total lodging cost for duration")
    food_total: float = Field(default=0.0, description="Estimated dining and food cost")
    activities_total: float = Field(default=0.0, description="Attraction entry fees and tour tickets")
    local_transport_total: float = Field(default=0.0, description="Local transit, taxi, and metro estimate")
    activities_and_food: float = Field(default=0.0, description="Combined attraction fees and meals estimate")
    breakdown: dict[str, float] = Field(default_factory=dict, description="Categorized itemized breakdown dictionary")
    budget_status: str = Field(default="within_budget", description="Status: 'within_budget', 'over_budget', or 'unconstrained'")
    over_budget: bool = Field(description="True if estimate exceeds budget")
    over_by_inr: float | None = Field(default=None, description="Amount exceeded")
    recommendations: list[str] = Field(default_factory=list, description="Practical cost-saving advice")
    within_budget_note: str | None = Field(default=None, description="Confirmation note if within budget")

