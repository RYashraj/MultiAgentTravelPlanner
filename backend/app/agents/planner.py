"""
Planner Agent: retrieves RAG memory context, then synthesises a full itinerary
using Gemini 2.0 Flash with real tool calls (weather + places).

Graph: START -> retrieve_memory -> merge -> END
"""
import json
import logging
from functools import lru_cache
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph
from pydantic import SecretStr

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
# Helper: determine budget tier from budget string
# ---------------------------------------------------------------------------

def _get_budget_tier(budget: str | None) -> str:
    budget_lower = (budget or "").lower()
    if any(w in budget_lower for w in ["luxury", "no limit", "unlimited", "5 star", "five star", "premium"]):
        return "luxury"
    elif any(w in budget_lower for w in ["budget", "cheap", "low", "backpack", "hostel", "friendly"]):
        return "budget"
    else:
        return "midrange"


# ---------------------------------------------------------------------------
# Graph nodes
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


def merge_node(state: AgentState) -> dict[str, Any]:
    """Uses Gemini with tool calling to fetch live data and generate the itinerary."""
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

    # Determine budget tier
    budget_tier = _get_budget_tier(budget)

    # Pre-fetch local context to inject into Gemini prompt
    loc_key = next(
        (k for k in MOCK_PLACES_DB.keys()
         if k.lower() in destination.lower() or destination.lower() in k.lower()),
        None
    )
    all_local_places = MOCK_PLACES_DB.get(loc_key, []) if loc_key else []
    budget_hotels = get_budget_hotels(all_local_places, budget or "")
    shopping_places = [p for p in all_local_places if p.get("type") == "shopping"]
    transport_info = get_transport_info(origin or "", destination)

    # Build hotel context string
    hotel_ctx = ""
    if budget_hotels:
        hotel_ctx = f"\n**{budget_tier.upper()} HOTELS TO RECOMMEND (with prices):**\n"
        for h in budget_hotels[:3]:
            hotel_ctx += f"- {h['name']}: {h['description']}\n"
    
    # Build shopping context string
    shopping_ctx = ""
    if shopping_places:
        shopping_ctx = "\n**REAL SHOPPING AREAS TO MENTION (with price ranges):**\n"
        for s in shopping_places[:6]:
            shopping_ctx += f"- {s['name']}: {s['description']}\n"

    api_key = get_settings().gemini_api_key
    gemini_success = False
    full_narrative = ""

    if api_key:
        try:
            llm = ChatGoogleGenerativeAI(
                model="gemini-3.5-flash",
                api_key=SecretStr(api_key),
                max_retries=1,
                timeout=30,
            )
            llm_with_tools = llm.bind_tools([get_weather, search_places])  # type: ignore[arg-type]

            coordinator_context = ""
            if research_info:
                coordinator_context = f"\n**Research Context:**\n{research_info}\n"

            system_content = f"""You are the VoyagerAI Planner Agent. You MUST follow these STRICT rules:

RULE 1 - BUDGET ENFORCEMENT: The user's budget is '{budget}' ({budget_tier.upper()} tier).
  - NEVER suggest 5-star or luxury hotels for budget/mid-range travellers.
  - ALWAYS recommend accommodation matching the budget tier.
{hotel_ctx}

RULE 2 - SHOPPING: Always mention SPECIFIC, REAL shop names and street markets.
  - NEVER say just "go shopping" — name the actual place (e.g., Fashion Street, Linking Road, Colaba Causeway).
{shopping_ctx}

RULE 3 - TRANSPORT: Always include a dedicated transport section.
  - Include how to get from {origin or 'origin city'} to {destination}.
  - Include train/flight options WITH PRICES (e.g., Shatabdi Express: ~7 hrs, Rs.700-1500).
{transport_info}

RULE 4 - PRICING: Include prices for everything:
  - Hotels: Rs./night
  - Restaurants: Rs. per person
  - Attractions: entry fees
  - Shopping: price ranges

RULE 5 - FORMAT: Write a beautiful Markdown itinerary with emojis, bold headers, day-by-day breakdown.

Now call the tools first, then write the itinerary following ALL rules above."""

            user_prompt = (
                f"Plan a **{budget_tier.upper()} BUDGET** trip to **{destination}** from **{origin or 'unspecified origin'}**.\n"
                f"- Duration: {duration_days} days\n"
                f"- Goal/Theme: {goal or 'general travel'}\n"
                f"- Dates/Season: {dates or 'flexible'}\n"
                f"- Budget: **{budget}** ({budget_tier} tier) — STRICTLY match this budget for hotels\n"
                f"- Interests/Preferences: {', '.join(preferences) if preferences else 'streetwear shopping, local food, sightseeing'}\n"
                f"- Past context: {memory_context or 'None'}\n"
                f"{coordinator_context}\n"
                "Steps:\n"
                "1. Call get_weather for the destination.\n"
                "2. Call search_places with query_type='all' to get places data.\n"
                "3. Write the full itinerary following ALL system rules:\n"
                "   - Transport section with prices from origin\n"
                "   - Budget-appropriate hotels with Rs./night prices\n"
                "   - Specific named shopping streets (Fashion Street, Linking Road, etc.) with price ranges\n"
                "   - Day-by-day plan with restaurants and their prices\n"
                "   - Travel tips"
            )

            messages: list[BaseMessage] = [
                SystemMessage(content=system_content),
                HumanMessage(content=user_prompt)
            ]

            # Step 1: LLM decides which tools to call
            response = llm_with_tools.invoke(messages)
            messages.append(response)

            # Step 2: Execute tool calls
            if isinstance(response, AIMessage) and response.tool_calls:
                logger.info("Planner: executing %d tool calls", len(response.tool_calls))
                for tc in response.tool_calls:
                    if tc["name"] == "get_weather":
                        tool_res = get_weather.invoke(tc["args"])
                    elif tc["name"] == "search_places":
                        tool_res = search_places.invoke(tc["args"])
                    else:
                        tool_res = "Unknown tool"
                    messages.append(ToolMessage(content=str(tool_res), tool_call_id=tc["id"], name=tc["name"]))

            # Step 3: Final synthesis — use bare llm (no tools) to prevent looping
            final_response = llm.invoke(messages)
            full_narrative = str(final_response.content) if final_response.content else ""
            gemini_success = True

        except Exception:
            logger.warning("Gemini Planner failed — using local fallback", exc_info=True)

    if not gemini_success:
        # Comprehensive local fallback
        w_data_raw = get_weather.invoke({"location": destination})
        p_data_raw = search_places.invoke({"location": destination, "query_type": "all"})

        try:
            w_data = json.loads(w_data_raw) if isinstance(w_data_raw, str) else w_data_raw
        except Exception:
            w_data = {}

        try:
            p_data = json.loads(p_data_raw) if isinstance(p_data_raw, str) else p_data_raw
        except Exception:
            p_data = []

        # Format weather
        if isinstance(w_data, dict):
            w_str = f"{w_data.get('temp', 'N/A')} — {w_data.get('condition', 'N/A')}. {w_data.get('forecast', '')}"
        else:
            w_str = str(w_data)

        # Sort places by type — use budget-filtered hotels
        places_by_type: dict[str, list] = {"attraction": [], "restaurant": [], "hotel": [], "shopping": []}
        for p in (p_data if isinstance(p_data, list) else []):
            ptype = p.get("type", "attraction")
            if ptype in places_by_type:
                places_by_type[ptype].append(p)
            else:
                places_by_type["attraction"].append(p)

        # Replace hotels with budget-filtered ones
        if budget_hotels:
            places_by_type["hotel"] = budget_hotels
        if shopping_places and not places_by_type["shopping"]:
            places_by_type["shopping"] = shopping_places

        # Build day-by-day content
        days_content = ""
        for day in range(1, min(duration_days + 1, 8)):
            days_content += f"\n## 🗓️ Day {day}\n"
            if day == 1:
                days_content += "**Arrival & Orientation**\n"
                days_content += f"- ✈️ Arrive in {destination} and check into your accommodation\n"
                if places_by_type["hotel"]:
                    h = places_by_type["hotel"][0]
                    days_content += f"- 🏨 **Recommended Stay**: {h.get('name', 'Local Hotel')} — {h.get('description', '')}\n"
                days_content += "- 🌆 Evening: Explore the local neighbourhood\n"
                if places_by_type["restaurant"]:
                    r = places_by_type["restaurant"][0]
                    days_content += f"- 🍽️ **Dinner**: {r.get('name', 'Local Restaurant')} — {r.get('description', '')}\n"
            elif day == 2 and places_by_type["shopping"]:
                days_content += "**Shopping & Street Markets Day**\n"
                days_content += "- 🚶 Morning: Local breakfast and street food\n"
                for s in places_by_type["shopping"][:3]:
                    days_content += f"- 🛍️ **{s.get('name')}** — {s.get('description', '')}\n"
                if len(places_by_type["restaurant"]) > 1:
                    r = places_by_type["restaurant"][1]
                    days_content += f"- 🍽️ **Lunch**: {r.get('name')} — {r.get('description', '')}\n"
            elif day <= len(places_by_type["attraction"]) + 2:
                idx = day - 3 if day > 2 else day - 2
                idx = max(0, idx)
                if idx < len(places_by_type["attraction"]):
                    a = places_by_type["attraction"][idx]
                    days_content += f"**Exploring {a.get('name', destination)}**\n"
                    days_content += f"- 🗺️ Visit **{a.get('name', 'Top Attraction')}** — {a.get('description', '')}\n"
                days_content += "- 🚶 Morning walk and local breakfast\n"
                rest_idx = idx + 2
                if rest_idx < len(places_by_type["restaurant"]):
                    r = places_by_type["restaurant"][rest_idx]
                    days_content += f"- 🍽️ **Lunch/Dinner**: {r.get('name', 'Local Eatery')} — {r.get('description', '')}\n"
            else:
                days_content += "**Free Exploration Day**\n"
                days_content += "- 🌅 Morning: Visit a local market or café\n"
                days_content += "- 🏙️ Afternoon: Revisit your favourite spots\n"
                days_content += "- 🌃 Evening: Farewell dinner at a top-rated local restaurant\n"

        # Build shopping section
        shopping_section = ""
        if places_by_type["shopping"]:
            shopping_section = "\n## 🛍️ Shopping Hotspots\n"
            for s in places_by_type["shopping"]:
                shopping_section += f"- **{s.get('name')}** — {s.get('description', '')}\n"

        full_narrative = (
            f"# 🌍 VoyagerAI Itinerary — {destination}\n"
            f"**{duration_days}-Day {goal or 'Travel'} Trip** | Budget: **{budget or 'Not specified'}** ({budget_tier}) | From: **{origin or 'your city'}**\n\n"
            f"---\n\n"
            f"{transport_info}\n\n"
            f"---\n\n"
            f"## 🌤️ Weather Forecast\n"
            f"**{w_str}**\n\n"
            f"---\n"
            f"{days_content}\n"
            f"{shopping_section}\n"
            f"---\n\n"
            f"## 💡 Travel Tips\n"
            f"- 💰 **Budget**: {budget or 'Plan ahead for best deals'} ({budget_tier} tier)\n"
            f"- 🗓️ **Best Time**: {dates or 'Year-round destination'}\n"
            f"- 📱 Use Google Maps for real-time navigation\n"
            f"- 🏧 Carry some local currency for street vendors and small shops\n"
            f"- 🌐 Get a local SIM card (Jio/Airtel) for data connectivity\n"
            f"- 🎟️ Book trains on IRCTC.co.in | Flights on MakeMyTrip/Goibibo\n"
            f"- 🛍️ Always bargain at street markets — start at 50% of the quoted price!\n"
        )

    planner_output = {
        "narrative": full_narrative,
        "gemini_used": gemini_success,
    }
    return {"agent_outputs": {**outputs, "planner": planner_output}}


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

_workflow = StateGraph(AgentState)
_workflow.add_node("retrieve_memory", retrieve_memory_node)
_workflow.add_node("merge", merge_node)

_workflow.add_edge(START, "retrieve_memory")
_workflow.add_edge("retrieve_memory", "merge")
_workflow.add_edge("merge", END)

planner_graph = _workflow.compile()
