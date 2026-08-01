"""
Flight Agent: specialized data agent wrapping Member A's search_flights tool.

Pure data node — zero LLM calls, zero natural language generation.
Reads planner state, validates input parameters, queries Amadeus flight tool,
and returns structured FlightOption objects for financial & itinerary synthesis.
"""
import json
import logging
import re
from typing import Any

from app.agents.state import AgentState
from app.schemas.bookings import FlightOption, parse_price_to_number
from app.tools.amadeus_tool import resolve_iata_code, search_flights

logger = logging.getLogger(__name__)



def flight_agent_node(state: AgentState) -> dict[str, Any]:
    """
    Executes flight search using search_flights tool.
    
    Reads:
        state['origin']: Origin city or airport code (e.g. 'Mumbai')
        state['destination']: Destination city or airport code (e.g. 'Goa')
        state['dates']: Target travel date (YYYY-MM-DD or string)
        
    Writes:
        state['agent_outputs']['flights']: Dict containing resolved IATA codes,
        structured FlightOption list, cheapest price info, and execution errors if any.
    """
    raw_origin = state.get("origin")
    raw_destination = state.get("destination")
    dates = state.get("dates")

    # 1. Validate required inputs with safe fallback defaults
    if not raw_origin:
        logger.info("FlightAgent: 'origin' missing in state — defaulting to 'BOM'")
        origin = "BOM"
    else:
        origin = raw_origin.strip()

    if not raw_destination:
        logger.info("FlightAgent: 'destination' missing in state — defaulting to 'GOI'")
        destination = "GOI"
    else:
        destination = raw_destination.strip()

    origin_iata = resolve_iata_code(origin)
    destination_iata = resolve_iata_code(destination)

    logger.info(
        "FlightAgent: Searching flights from %s (%s) to %s (%s) for date: %s...",
        origin, origin_iata, destination, destination_iata, dates or "Flexible"
    )

    flight_options: list[FlightOption] = []
    error_msg: str | None = None

    # 2. Call search_flights tool with failure handling
    try:
        tool_res = search_flights.invoke({
            "origin": origin_iata,
            "destination": destination_iata,
            "date": dates
        })
        
        raw_list = json.loads(tool_res) if isinstance(tool_res, str) else (tool_res or [])
        if isinstance(raw_list, list):
            for item in raw_list:
                if not isinstance(item, dict):
                    continue
                p_str = item.get("price", "N/A")
                p_num = parse_price_to_number(p_str)

                
                # Construct & validate structured FlightOption schema
                flight_opt = FlightOption(
                    carrier=item.get("carrier", "Airline"),
                    flight_number=item.get("flight_number", "FL-101"),
                    departure_time=item.get("departure_time", "09:00"),
                    arrival_time=item.get("arrival_time", "11:15"),
                    price=p_str,
                    duration=item.get("duration", "2h 00m"),
                    cabin=item.get("cabin", "Economy"),
                    price_inr=p_num
                )
                flight_options.append(flight_opt)
    except Exception as exc:
        logger.warning("FlightAgent tool call failed (%s) — returning empty flight options list", exc)
        error_msg = str(exc)

    # 3. Calculate cheapest fare metrics
    cheapest_price_str: str | None = None
    cheapest_price_num: float | None = None

    for opt in flight_options:
        if opt.price_inr is not None:
            if cheapest_price_num is None or opt.price_inr < cheapest_price_num:
                cheapest_price_num = opt.price_inr
                cheapest_price_str = opt.price

    # Convert Pydantic models to serializable dicts for LangGraph state compatibility
    flights_serialized = [opt.model_dump() for opt in flight_options]

    flights_output = {
        "origin_iata": origin_iata,
        "destination_iata": destination_iata,
        "flights": flights_serialized,
        "cheapest_price_str": cheapest_price_str or "N/A",
        "cheapest_price_inr": cheapest_price_num,
        "error": error_msg
    }

    outputs = dict(state.get("agent_outputs") or {})
    return {"agent_outputs": {**outputs, "flights": flights_output}}

