"""
Planner Agent: orchestrates specialized agent nodes (weather, places, flights, hotels, budget)
and synthesizes a complete, highly personalized itinerary using a single Gemini call.

Graph:
  START -> retrieve_memory -> [weather_agent, places_agent, flight_agent, hotel_agent] -> budget_agent -> synthesize -> END
"""
import json
import logging
from functools import lru_cache
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph
from pydantic import SecretStr

from app.agents.budget_agent import budget_agent_node
from app.agents.flight_agent import flight_agent_node
from app.agents.hotel_agent import hotel_agent_node, _get_budget_tier
from app.agents.state import AgentState
from app.core.config import get_settings
from app.tools.places_tool import (
    MOCK_PLACES_DB,
    get_budget_hotels,
    get_transport_info,
    search_places,
)
from app.tools.weather_tool import get_weather

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Singleton ChromaDB store
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_chroma_store():
    """Lazily create the ChromaMemoryStore singleton once per process."""
    try:
        from app.rag.chroma_store import ChromaMemoryStore
        return ChromaMemoryStore()
    except Exception as exc:
        logger.warning("ChromaDB unavailable: %s — memory retrieval disabled", exc)
        return None


# ---------------------------------------------------------------------------
# Graph Nodes
# ---------------------------------------------------------------------------

def retrieve_memory_node(state: AgentState) -> dict[str, Any]:
    """Retrieves relevant past trip context from ChromaDB (best-effort)."""
    trip_id = state.get("trip_id", "")
    user_message = state.get("user_message", "")

    if not trip_id or not user_message:
        return {"memory_context": []}

    store = _get_chroma_store()
    if store is None:
        return {"memory_context": []}

    try:
        memory_context = store.retrieve_context(trip_id=trip_id, query=user_message, k=5)
    except Exception as exc:
        logger.warning("Memory retrieval failed: %s", exc)
        memory_context = []

    return {"memory_context": memory_context}


def weather_agent_node(state: AgentState) -> dict[str, Any]:
    """Fetches weather data for destination."""
    destination = state.get("destination", "")
    try:
        w_raw = get_weather.invoke({"location": destination})
        w_data = json.loads(w_raw) if isinstance(w_raw, str) else (w_raw or {})
    except Exception:
        w_data = {"temp": "25°C", "condition": "Clear", "forecast": "Pleasant weather."}

    w_output = {
        "temp": w_data.get("temp", "25°C"),
        "condition": w_data.get("condition", "Clear"),
        "forecast": w_data.get("forecast", "Pleasant weather expected."),
        "raw": str(w_data)
    }
    outputs = dict(state.get("agent_outputs") or {})
    return {"agent_outputs": {**outputs, "weather": w_output}}


def places_agent_node(state: AgentState) -> dict[str, Any]:
    """Fetches attractions, restaurants, shopping, and transport info."""
    destination = state.get("destination", "")
    origin = state.get("origin", "")
    budget = state.get("budget", "")

    try:
        p_raw = search_places.invoke({"location": destination, "query_type": "all"})
        places_list = json.loads(p_raw) if isinstance(p_raw, str) else (p_raw or [])
    except Exception:
        places_list = []

    loc_key = next(
        (k for k in MOCK_PLACES_DB.keys()
         if k.lower() in destination.lower() or destination.lower() in k.lower()),
        None
    )
    all_local = MOCK_PLACES_DB.get(loc_key, []) if loc_key else places_list

    attractions = [p for p in all_local if p.get("type", "attraction") == "attraction"]
    restaurants = [p for p in all_local if p.get("type") == "restaurant"]
    shopping = [p for p in all_local if p.get("type") == "shopping"]
    budget_hotels = get_budget_hotels(all_local, budget or "")
    transport_info = get_transport_info(origin or "", destination)

    places_output = {
        "all": all_local,
        "attractions": attractions,
        "restaurants": restaurants,
        "shopping": shopping,
        "budget_hotels": budget_hotels,
        "transport_info": transport_info
    }
    outputs = dict(state.get("agent_outputs") or {})
    return {"agent_outputs": {**outputs, "places": places_output}}


def synthesize_node(state: AgentState) -> dict[str, Any]:
    """
    Synthesizes final itinerary using pre-fetched outputs from all specialized agents.
    Executes exactly ONE Gemini call (without tool binding).
    """
    destination = state.get("destination", "")
    origin = state.get("origin", "")
    dates = state.get("dates")
    budget = state.get("budget")
    goal = state.get("goal")
    duration_days = state.get("duration_days") or 3
    preferences = list(state.get("preferences") or [])
    memory_context = list(state.get("memory_context") or [])
    outputs = dict(state.get("agent_outputs") or {})

    research_info = outputs.get("research", {}).get("result", "")
    weather_data = outputs.get("weather", {})
    places_data = outputs.get("places", {})
    flights_data = outputs.get("flights", {})
    hotels_data = outputs.get("hotels", {})
    budget_analysis = outputs.get("budget_analysis", {})

    budget_tier = _get_budget_tier(budget)

    # Format flight options context
    flight_options_str = "No direct flight data available."
    if flights_data.get("flights"):
        flight_options_str = "\n".join([
            f"- {f.get('carrier')} {f.get('flight_number')}: {f.get('departure_time')} -> {f.get('arrival_time')} ({f.get('duration')}) — Price: {f.get('price')}"
            for f in flights_data["flights"][:3]
        ])

    # Format hotel options context
    hotel_options_str = "No specific hotel data available."
    if hotels_data.get("hotels"):
        hotel_options_str = "\n".join([
            f"- {h.get('name')}: {h.get('price_per_night')}/night ({h.get('room_type')}) — {h.get('description')}"
            for h in hotels_data["hotels"][:3]
        ])

    # Format budget analysis context
    budget_recommendations_str = ""
    if budget_analysis.get("over_budget"):
        budget_recommendations_str = "\n**BUDGET OVERRUN WARNING & COST RECOMMENDATIONS:**\n"
        for rec in budget_analysis.get("recommendations", []):
            budget_recommendations_str += f"- ⚠️ {rec}\n"
    elif budget_analysis.get("within_budget_note"):
        budget_recommendations_str = f"\n**Budget Status:** {budget_analysis['within_budget_note']}\n"

    # Format shopping context
    shopping_ctx = ""
    if places_data.get("shopping"):
        shopping_ctx = "\n**RECOMMENDED SHOPPING SPOTS:**\n"
        for s in places_data["shopping"][:5]:
            shopping_ctx += f"- {s.get('name')}: {s.get('description')}\n"

    api_key = get_settings().gemini_api_key
    gemini_success = False
    full_narrative = ""

    if api_key:
        try:
            llm = ChatGoogleGenerativeAI(
                model="gemini-1.5-flash",
                api_key=SecretStr(api_key),
                max_retries=1,
                timeout=30,
            )

            system_content = f"""You are VoyagerAI, the master travel planning assistant.
Synthesize the provided research, weather, flight, hotel, places, and budget data into a comprehensive Markdown travel itinerary.

STRICT INSTRUCTIONS:
1. BUDGET & FLIGHTS:
   - Include flight options from {origin or 'origin'} to {destination}.
   - Mention the recommended hotels matching budget tier '{budget_tier.upper()}'.
   - Include budget status and any money-saving recommendations provided below.

2. SHOPPING & SPOTS:
   - Recommend specific named attractions, restaurants, and shopping areas from the context.

3. PRICING & TIPS:
   - Provide realistic price quotes for hotels, meals, transport, and entry fees.

4. FORMATTING:
   - Structure into clear sections: Overview & Budget Summary, Transport & Flights, Accommodations, Weather, Day-by-Day Itinerary, Shopping & Culture, Practical Travel Tips.
"""

            user_prompt = (
                f"# TRIP DESTINATION: {destination} (From {origin or 'Unspecified'})\n"
                f"- Duration: {duration_days} days | Dates: {dates or 'Flexible'}\n"
                f"- User Budget: {budget or 'Unspecified'} ({budget_tier.upper()} tier)\n"
                f"- Purpose/Goal: {goal or 'Sightseeing & Vacation'}\n"
                f"- User Preferences: {', '.join(preferences) if preferences else 'Local food, sightseeing, shopping'}\n\n"
                f"## PRE-FETCHED RESEARCH DATA:\n"
                f"**Weather Forecast**: {weather_data.get('temp')} - {weather_data.get('condition')}. {weather_data.get('forecast')}\n\n"
                f"**Flight Options**:\n{flight_options_str}\n\n"
                f"**Hotel Accommodations ({budget_tier.upper()})**:\n{hotel_options_str}\n\n"
                f"**Ground Transport Info**:\n{places_data.get('transport_info', '')}\n\n"
                f"{budget_recommendations_str}\n"
                f"{shopping_ctx}\n"
                f"**Past Context**: {memory_context or 'None'}\n\n"
                "Please generate the complete, beautifully formatted Markdown itinerary now."
            )

            messages: list[BaseMessage] = [
                SystemMessage(content=system_content),
                HumanMessage(content=user_prompt)
            ]

            # SINGLE Gemini invocation — no tool calls
            response = llm.invoke(messages)
            full_narrative = str(response.content) if response.content else ""
            gemini_success = True

        except Exception as exc:
            logger.warning("Gemini Planner synthesis failed (%s) — using local fallback", exc)

    if not gemini_success:
        # Comprehensive local fallback narrative
        w_str = f"{weather_data.get('temp', '25°C')} — {weather_data.get('condition', 'Clear')}. {weather_data.get('forecast', '')}"
        
        days_content = ""
        attractions = places_data.get("attractions") or []
        restaurants = places_data.get("restaurants") or []
        shopping = places_data.get("shopping") or []
        hotels = hotels_data.get("hotels") or []
        flights = flights_data.get("flights") or []

        for day in range(1, min(duration_days + 1, 8)):
            days_content += f"\n## 🗓️ Day {day}\n"
            if day == 1:
                days_content += f"**Arrival in {destination} & Check-in**\n"
                if flights:
                    f_opt = flights[0]
                    days_content += f"- ✈️ **Flight Option**: {f_opt.get('carrier')} {f_opt.get('flight_number')} ({f_opt.get('price')})\n"
                if hotels:
                    h_opt = hotels[0]
                    days_content += f"- 🏨 **Recommended Stay**: {h_opt.get('name')} ({h_opt.get('price_per_night')})\n"
                if restaurants:
                    r_opt = restaurants[0]
                    days_content += f"- 🍽️ **Dinner**: {r_opt.get('name')} — {r_opt.get('description')}\n"
            elif day == 2 and shopping:
                days_content += "**Explore Markets & Local Shopping**\n"
                for s in shopping[:3]:
                    days_content += f"- 🛍️ **{s.get('name')}** — {s.get('description')}\n"
            elif attractions:
                idx = (day - 2) % len(attractions)
                att = attractions[idx]
                days_content += f"**Discover {att.get('name')}**\n"
                days_content += f"- 🗺️ **Attraction**: {att.get('name')} — {att.get('description')}\n"
                if restaurants and len(restaurants) > 1:
                    r = restaurants[min(day, len(restaurants)-1)]
                    days_content += f"- 🍽️ **Eatery**: {r.get('name')} — {r.get('description')}\n"
            else:
                days_content += "**Sightseeing & City Walk**\n"
                days_content += f"- 🌆 Explore local neighborhood cafes and cultural landmarks in {destination}.\n"

        budget_warning_block = ""
        if budget_analysis.get("over_budget"):
            budget_warning_block = "\n> ⚠️ **BUDGET ADVISORY:**\n"
            for rec in budget_analysis.get("recommendations", []):
                budget_warning_block += f"> - {rec}\n"

        full_narrative = (
            f"# 🌍 VoyagerAI Itinerary — {destination}\n"
            f"**{duration_days}-Day {goal or 'Travel'} Plan** | Budget: **{budget or 'Flexible'}** ({budget_tier.upper()}) | From: **{origin or 'Your City'}**\n\n"
            f"---\n\n"
            f"{places_data.get('transport_info', '')}\n\n"
            f"### ✈️ Flight Recommendations ({flights_data.get('origin_iata', 'BOM')} → {flights_data.get('destination_iata', 'GOI')})\n"
            f"{flight_options_str}\n\n"
            f"### 🏨 Hotel Recommendations ({budget_tier.upper()})\n"
            f"{hotel_options_str}\n\n"
            f"{budget_warning_block}\n"
            f"---\n\n"
            f"## 🌤️ Weather Forecast\n"
            f"**{w_str}**\n\n"
            f"---\n"
            f"{days_content}\n"
            f"---\n\n"
            f"## 💡 Practical Travel Tips\n"
            f"- 💰 **Estimated Trip Total**: ~₹{int(budget_analysis.get('estimated_total_inr', 10000)):,}\n"
            f"- 🗓️ **Travel Season**: {dates or 'Flexible'}\n"
            f"- 📱 Download offline Google Maps & transportation apps\n"
            f"- 🎟️ Book flights and hotels at least 2 weeks in advance for optimal rates\n"
        )

    planner_output = {
        "itinerary": full_narrative,
        "narrative": full_narrative,
        "flights": flights_data,
        "hotels": hotels_data,
        "budget": budget_analysis,
        "gemini_used": gemini_success,
    }
    outputs = dict(state.get("agent_outputs") or {})
    return {"agent_outputs": {**outputs, "planner": planner_output}}



# ---------------------------------------------------------------------------
# Graph Assembly
# ---------------------------------------------------------------------------

_workflow = StateGraph(AgentState)

_workflow.add_node("retrieve_memory", retrieve_memory_node)
_workflow.add_node("weather_agent", weather_agent_node)
_workflow.add_node("places_agent", places_agent_node)
_workflow.add_node("flight_agent", flight_agent_node)
_workflow.add_node("hotel_agent", hotel_agent_node)
_workflow.add_node("budget_agent", budget_agent_node)
_workflow.add_node("synthesize", synthesize_node)

_workflow.add_edge(START, "retrieve_memory")

# Parallel fan-out from retrieve_memory
_workflow.add_edge("retrieve_memory", "weather_agent")
_workflow.add_edge("retrieve_memory", "places_agent")
_workflow.add_edge("retrieve_memory", "flight_agent")
_workflow.add_edge("retrieve_memory", "hotel_agent")

# Fan-in to budget_agent
_workflow.add_edge("weather_agent", "budget_agent")
_workflow.add_edge("places_agent", "budget_agent")
_workflow.add_edge("flight_agent", "budget_agent")
_workflow.add_edge("hotel_agent", "budget_agent")

# Sequential to synthesize and END
_workflow.add_edge("budget_agent", "synthesize")
_workflow.add_edge("synthesize", END)

planner_graph = _workflow.compile()
