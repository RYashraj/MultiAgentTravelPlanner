"""
Budget Agent: specialized financial agent analyzing travel costs and budget feasibility.

Pure data node — zero LLM calls, zero natural language text responses.
Aggregates flights, hotels, food, activities, and local transport estimates.
Generates structured BudgetBreakdown schema outputs and actionable cost recommendations.
"""
import logging
import re
from typing import Any

from app.agents.state import AgentState
from app.schemas.bookings import BudgetBreakdown

logger = logging.getLogger(__name__)


def _parse_numeric_budget(budget_str: str | None) -> float | None:
    """
    Parses user budget string input into numeric float value (INR).
    Converts USD to INR if specified (approx 1 USD = 85 INR).
    Returns None if budget is unlimited, luxury, or unconstrained.
    """
    if not budget_str:
        return None

    s = budget_str.lower().strip()
    if any(w in s for w in ["no limit", "unlimited", "luxury"]):
        return None  # No budget constraint

    # Search for numbers (e.g., ₹50,000, 50000 INR, $1000, 1000 USD)
    s_clean = s.replace(",", "")
    match = re.search(r"(\d+)", s_clean)
    if match:
        val = float(match.group(1))
        if "$" in s or "usd" in s:
            val *= 85.0  # Approx USD to INR conversion rate
        return val

    return None


def _extract_activity_costs_from_places(attractions: list[dict]) -> float:
    """
    Extracts ticket/entry fees from attraction descriptions if present.
    Sums up all parsed prices found in attraction descriptions.
    """
    found_prices: list[float] = []
    for item in attractions:
        desc = item.get("description", "")
        matches = re.findall(r"₹\s*(\d+)", desc)
        for m in matches:
            try:
                found_prices.append(float(m))
            except ValueError:
                pass
    return sum(found_prices) if found_prices else 0.0


def budget_agent_node(state: AgentState) -> dict[str, Any]:
    """
    Aggregates trip costs across 5 core categories:
      1. Flights (round-trip per person)
      2. Hotels (nightly rate x duration)
      3. Food & Dining estimate
      4. Activities & Entry fees
      5. Local Transport (taxis, metro, auto)
      
    Calculates subtotal, total, checks user budget feasibility, and returns
    structured BudgetBreakdown schema output with practical recommendations.
    
    Reads:
        state['agent_outputs']['flights']
        state['agent_outputs']['hotels']
        state['agent_outputs']['places']
        state['duration_days']
        state['budget']
        
    Writes:
        state['agent_outputs']['budget_analysis']: Structured BudgetBreakdown dict
    """
    outputs = dict(state.get("agent_outputs") or {})
    duration_days = state.get("duration_days") or 3
    budget_raw = state.get("budget")

    flights_data = outputs.get("flights", {})
    hotels_data = outputs.get("hotels", {})
    places_data = outputs.get("places", {})

    # 1. Flights Aggregation (Handling missing flight data gracefully)
    flight_unit = flights_data.get("cheapest_price_inr")
    if flight_unit is not None:
        flight_round_trip = float(flight_unit) * 2.0
    else:
        logger.info("BudgetAgent: Flight fare data missing — using fallback estimate of ₹8,000 round-trip")
        flight_round_trip = 8000.0

    # 2. Hotels Aggregation (Handling missing hotel data gracefully)
    hotel_nightly = hotels_data.get("cheapest_price_inr")
    if hotel_nightly is not None:
        hotel_total = float(hotel_nightly) * float(duration_days)
    else:
        logger.info("BudgetAgent: Hotel rate data missing — using fallback estimate of ₹1,500/night across %d days", duration_days)
        hotel_total = 1500.0 * float(duration_days)

    # 3. Food Estimate (₹800/day per person)
    food_total = float(duration_days) * 800.0

    # 4. Activities & Ticket Fees Estimate
    attractions = places_data.get("attractions") or []
    extracted_fees = _extract_activity_costs_from_places(attractions)
    activities_total = extracted_fees if extracted_fees > 0 else (float(duration_days) * 500.0)

    # 5. Local Transport Estimate (₹400/day for cabs/metro/auto)
    local_transport_total = float(duration_days) * 400.0

    # Financial Aggregation
    subtotal = flight_round_trip + hotel_total + food_total + activities_total + local_transport_total
    estimated_total = subtotal  # Total cost

    user_budget_inr = _parse_numeric_budget(budget_raw)

    over_budget = False
    over_by_inr: float | None = None
    budget_status = "within_budget"
    recommendations: list[str] = []

    # 6. Budget Status & Practical Cost Recommendations Generation
    if user_budget_inr is not None:
        if estimated_total > user_budget_inr:
            over_budget = True
            budget_status = "over_budget"
            over_by_inr = estimated_total - user_budget_inr

            # Practical recommendation 1: Hotel cost reduction
            if hotel_total > (user_budget_inr * 0.35):
                recommendations.append(
                    f"Choose cheaper hotels or hostels: Switching to budget dorms/hostels can save ~₹{int(hotel_total * 0.5):,} across {duration_days} nights."
                )

            # Practical recommendation 2: Flight / Transit cost reduction
            if flight_round_trip > (user_budget_inr * 0.35):
                recommendations.append(
                    f"Cheaper transport: Consider train or bus transit instead of flights to save up to ₹{int(flight_round_trip * 0.6):,}."
                )

            # Practical recommendation 3: Reduce stay duration
            if duration_days > 2 and over_by_inr > 1500:
                recommendations.append(
                    f"Reduce stay duration: Shortening your trip to {duration_days - 1} days fits your budget limit."
                )

            # Practical recommendation 4: Off-peak & Weekday travel
            recommendations.append(
                "Travel weekdays / off-peak: Booking flights and stays on Tuesday–Thursday typically yields 15–25% lower fares."
            )
        else:
            budget_status = "within_budget"
    else:
        budget_status = "unconstrained"

    within_note: str | None = None
    if not over_budget and user_budget_inr is not None:
        within_note = f"Estimated total (₹{int(estimated_total):,}) is well within your budget limit of ₹{int(user_budget_inr):,}!"

    category_breakdown = {
        "flights": flight_round_trip,
        "hotels": hotel_total,
        "food": food_total,
        "activities": activities_total,
        "local_transport": local_transport_total
    }

    # 7. Construct & Validate Pydantic Schema
    breakdown_schema = BudgetBreakdown(
        user_budget_str=budget_raw or "Not specified",
        user_budget_inr=user_budget_inr,
        subtotal=subtotal,
        estimated_total_inr=estimated_total,
        flight_round_trip=flight_round_trip,
        hotel_total=hotel_total,
        food_total=food_total,
        activities_total=activities_total,
        local_transport_total=local_transport_total,
        activities_and_food=activities_total + food_total,
        breakdown=category_breakdown,
        budget_status=budget_status,
        over_budget=over_budget,
        over_by_inr=over_by_inr,
        recommendations=recommendations,
        within_budget_note=within_note
    )

    logger.info(
        "BudgetAgent: Subtotal ₹%.2f, Total ₹%.2f (User Budget: %s, Status: %s)",
        subtotal, estimated_total, budget_raw, budget_status
    )

    outputs_dict = breakdown_schema.model_dump()

    return {"agent_outputs": {**outputs, "budget_analysis": outputs_dict}}

