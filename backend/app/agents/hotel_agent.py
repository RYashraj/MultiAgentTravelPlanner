"""
Hotel Agent: specialized data agent wrapping Member A's search_hotels tool.

Pure data node — zero LLM calls, zero natural language generation.
Reads planner state, classifies budget tier, queries Amadeus hotel tool,
and returns structured HotelOption objects for financial & itinerary synthesis.
"""
import json
import logging
import re
from typing import Any

from app.agents.state import AgentState
from app.schemas.bookings import HotelOption, parse_price_to_number
from app.tools.amadeus_tool import resolve_iata_code, search_hotels

logger = logging.getLogger(__name__)


def _get_budget_tier(budget: str | None) -> str:
    """
    Determines the target accommodation budget tier ('budget', 'midrange', or 'luxury')
    from the raw user budget string input.
    """
    budget_lower = (budget or "").lower().strip()
    if any(w in budget_lower for w in ["luxury", "no limit", "unlimited", "5 star", "five star", "premium"]):
        return "luxury"
    elif any(w in budget_lower for w in ["budget", "cheap", "low", "backpack", "hostel", "friendly"]):
        return "budget"
    else:
        return "midrange"



def hotel_agent_node(state: AgentState) -> dict[str, Any]:
    """
    Executes hotel search using search_hotels tool.
    
    Reads:
        state['destination']: Target city or location name (e.g. 'Goa', 'Delhi')
        state['dates']: Target check-in date (YYYY-MM-DD or string)
        state['budget']: Raw user budget input (e.g. 'Luxury $5000' or 'Budget-friendly')
        
    Writes:
        state['agent_outputs']['hotels']: Dict containing destination IATA code,
        budget tier, structured HotelOption list, cheapest price metrics, and errors if any.
    """
    raw_destination = state.get("destination")
    budget_raw = state.get("budget")
    dates = state.get("dates")

    # 1. Input Validation & Safe Fallbacks
    if not raw_destination:
        logger.info("HotelAgent: 'destination' missing in state — defaulting to 'GOI'")
        destination = "GOI"
    else:
        destination = raw_destination.strip()

    destination_iata = resolve_iata_code(destination)
    budget_tier = _get_budget_tier(budget_raw)

    logger.info(
        "HotelAgent: Searching %s tier hotels in %s (%s) for date: %s...",
        budget_tier.upper(), destination, destination_iata, dates or "Flexible"
    )

    hotel_options: list[HotelOption] = []
    error_msg: str | None = None

    # 2. Invoke search_hotels Tool with Failure Handling
    try:
        tool_res = search_hotels.invoke({
            "location": destination_iata,
            "check_in": dates,
            "budget_tier": budget_tier
        })
        raw_list = json.loads(tool_res) if isinstance(tool_res, str) else (tool_res or [])
        if isinstance(raw_list, list):
            for item in raw_list:
                if not isinstance(item, dict):
                    continue
                p_str = item.get("price_per_night", "N/A")
                p_num = parse_price_to_number(p_str)


                # Construct & validate structured HotelOption schema
                hotel_opt = HotelOption(
                    name=item.get("name", "Local Hotel"),
                    price_per_night=p_str,
                    currency=item.get("currency", "INR"),
                    room_type=item.get("room_type", "Standard Room"),
                    description=item.get("description", "Comfortable local accommodation."),
                    price_inr=p_num
                )
                hotel_options.append(hotel_opt)
    except Exception as exc:
        logger.warning("HotelAgent tool call failed (%s) — returning empty hotel list", exc)
        error_msg = str(exc)

    # 3. Calculate cheapest nightly rate metrics
    cheapest_price_str: str | None = None
    cheapest_price_num: float | None = None

    for opt in hotel_options:
        if opt.price_inr is not None:
            if cheapest_price_num is None or opt.price_inr < cheapest_price_num:
                cheapest_price_num = opt.price_inr
                cheapest_price_str = opt.price_per_night

    # Convert Pydantic models to serializable dicts for LangGraph state compatibility
    hotels_serialized = [opt.model_dump() for opt in hotel_options]

    hotels_output = {
        "destination_iata": destination_iata,
        "budget_tier": budget_tier,
        "hotels": hotels_serialized,
        "cheapest_price_str": cheapest_price_str or "N/A",
        "cheapest_price_inr": cheapest_price_num,
        "error": error_msg
    }

    outputs = dict(state.get("agent_outputs") or {})
    return {"agent_outputs": {**outputs, "hotels": hotels_output}}

