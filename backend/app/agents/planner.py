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
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langgraph.graph import END, START, StateGraph

from app.agents.gemini_client import call_gemini
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
    attractions_info = outputs.get("attractions", {}).get("summary", "")
    weather_info = outputs.get("weather", {})

    # Determine budget tier
    budget_tier = _get_budget_tier(budget)

    # Pre-fetch local context to inject into Gemini prompt
    loc_key = next(
        (k for k in MOCK_PLACES_DB
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
            coordinator_context = ""
            if research_info:
                coordinator_context = f"\n**Research Context:**\n{research_info}\n"
            if attractions_info:
                coordinator_context += f"\n**Top Attractions (from AttractionAgent):**\n{attractions_info[:400]}\n"
            if weather_info:
                w_temp = weather_info.get('temp', '')
                w_cond = weather_info.get('condition', '')
                w_tips = str(weather_info.get('packing_tips') or weather_info.get('forecast') or '')
                if w_temp or w_cond:
                    coordinator_context += f"\n**Weather Context:** {w_temp}, {w_cond}. {w_tips[:150]}\n"

            goal_lower = (goal or "").lower()
            is_shopping_goal = any(w in goal_lower for w in ["shop", "streetwear", "fashion", "market", "buy", "mall", "bazar", "bazaar"])
            is_food_goal = any(w in goal_lower for w in ["food", "eat", "restaurant", "cuisine", "dine"])
            is_adventure_goal = any(w in goal_lower for w in ["adventure", "trek", "hike", "outdoor", "sport"])

            if is_shopping_goal:
                goal_rule = (
                    f"RULE 0 - GOAL PRIORITY (MOST IMPORTANT):\n"
                    f"  The user's MAIN GOAL is SHOPPING/STREETWEAR. This is NOT optional.\n"
                    f"  - At least 50-60% of days (i.e., {max(1, int(duration_days * 0.6))} out of {duration_days} days) MUST be dedicated primarily to shopping.\n"
                    f"  - Spread shopping across MULTIPLE days — do NOT cram all shopping into 1 day.\n"
                    f"  - Each shopping day should cover DIFFERENT areas/markets (not the same places repeated).\n"
                    f"  - Sightseeing and historic spots should be SECONDARY — only 1-2 days at most.\n"
                    f"  - If the user says 'streetwear', focus on sneaker shops, hypebeast stores, thrift/vintage markets.\n"
                )
            elif is_food_goal:
                goal_rule = (
                    f"RULE 0 - GOAL PRIORITY (MOST IMPORTANT):\n"
                    f"  The user's MAIN GOAL is FOOD/DINING. Plan a food-first itinerary.\n"
                    f"  - Every day must include 2-3 SPECIFIC named restaurants or food experiences.\n"
                    f"  - Include food tours, street food walks, local market tastings.\n"
                    f"  - Attractions should be food-compatible (e.g., near good restaurants).\n"
                )
            elif is_adventure_goal:
                goal_rule = (
                    f"RULE 0 - GOAL PRIORITY (MOST IMPORTANT):\n"
                    f"  The user's MAIN GOAL is ADVENTURE/OUTDOORS.\n"
                    f"  - Prioritize outdoor activities, treks, and sports every single day.\n"
                    f"  - Minimize city sightseeing and shopping days.\n"
                )
            else:
                goal_rule = (
                    f"RULE 0 - GOAL PRIORITY (MOST IMPORTANT):\n"
                    f"  The user's main goal is: '{goal or 'general travel'}'.\n"
                    f"  - Structure the MAJORITY of days around this goal.\n"
                    f"  - Do NOT default to a generic arrive-sightsee-depart pattern.\n"
                )

            system_content = f"""{goal_rule}

RULE 1 - BUDGET ENFORCEMENT: The user's budget is '{budget}' ({budget_tier.upper()} tier). Max budget cap: stay within this limit.
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
  - DO NOT repeat the same "arrive and explore" pattern every trip.
  - Make each day feel distinct and purposeful toward the user's goal.

Now write the comprehensive, beautifully formatted Markdown itinerary following ALL rules above."""

            user_prompt = (
                f"Plan a **{budget_tier.upper()} BUDGET** trip to **{destination}** from **{origin or 'unspecified origin'}**.\n"
                f"- Duration: {duration_days} days\n"
                f"- Goal/Theme: {goal or 'general travel'}\n"
                f"- Dates/Season: {dates or 'flexible'}\n"
                f"- Budget: **{budget}** ({budget_tier} tier) — STRICTLY match this budget for hotels\n"
                f"- Interests/Preferences: {', '.join(preferences) if preferences else 'streetwear shopping, local food, sightseeing'}\n"
                f"- Past context: {memory_context or 'None'}\n"
                f"{coordinator_context}\n"
                "Write the full itinerary following ALL system rules:\n"
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

            full_narrative = call_gemini(messages, timeout=20, tools=[get_weather, search_places])
            gemini_success = bool(full_narrative and full_narrative.strip())

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

        # Build goal-aware day distribution
        goal_lower = (goal or "").lower()
        is_shopping_goal = any(w in goal_lower for w in ["shop", "streetwear", "fashion", "market", "buy", "mall", "bazar", "bazaar"])

        for day in range(1, min(duration_days + 1, 11)):
            days_content += f"\n## 🗓️ Day {day}\n"
            if day == 1:
                days_content += "**Arrival & Check-in**\n"
                days_content += f"- ✈️ Arrive in {destination} from {origin or 'your city'} and check into your accommodation\n"
                if places_by_type["hotel"]:
                    h = places_by_type["hotel"][0]
                    days_content += f"- 🏨 **Stay**: {h.get('name', 'Local Hotel')} — {h.get('description', '')}\n"
                days_content += "- 🌆 Evening: Settle in, grab dinner nearby\n"
                if places_by_type["restaurant"]:
                    r = places_by_type["restaurant"][0]
                    days_content += f"- 🍽️ **Dinner**: {r.get('name', 'Local Restaurant')} — {r.get('description', '')}\n"
            elif day == duration_days:
                days_content += "**Departure Day**\n"
                days_content += "- 🌅 Morning: Last-minute shopping or breakfast at a local café\n"
                days_content += f"- 🧳 Check out and head to the airport/station\n"
                days_content += f"- ✈️ Return to {origin or 'home'}\n"
            elif is_shopping_goal:
                # Shopping-goal: most days are shopping days, 1-2 days for sights
                num_sight_days = max(1, duration_days // 5)  # ~20% for sightseeing
                # Day 2 to (duration-num_sight_days-1) = shopping days
                shopping_day_idx = day - 2  # 0-indexed shopping days
                total_shopping_days = duration_days - 2 - num_sight_days
                if shopping_day_idx < total_shopping_days:
                    # This is a shopping day
                    shop_slice_start = (shopping_day_idx * 2) % max(1, len(places_by_type["shopping"]))
                    day_shops = places_by_type["shopping"][shop_slice_start:shop_slice_start + 2]
                    if not day_shops and places_by_type["shopping"]:
                        day_shops = [places_by_type["shopping"][shopping_day_idx % len(places_by_type["shopping"])]]
                    area_name = day_shops[0].get("name", "Shopping District") if day_shops else "Local Market"
                    days_content += f"**Shopping Day {shopping_day_idx + 1} — {area_name} area**\n"
                    days_content += "- 🌅 Morning: Local breakfast before heading out\n"
                    for s in day_shops:
                        days_content += f"- 🛍️ **{s.get('name')}** — {s.get('description', '')}\n"
                    days_content += "- 🍜 Afternoon: Street food lunch between shops\n"
                    # Rotate restaurants
                    r_idx = shopping_day_idx % max(1, len(places_by_type["restaurant"]))
                    if places_by_type["restaurant"]:
                        r = places_by_type["restaurant"][r_idx]
                        days_content += f"- 🍽️ **Dinner**: {r.get('name')} — {r.get('description', '')}\n"
                    days_content += "- 💡 Tip: Bargain hard at markets, start at 40-50% of quoted price\n"
                else:
                    # Sightseeing day
                    sight_idx = shopping_day_idx - total_shopping_days
                    if sight_idx < len(places_by_type["attraction"]):
                        a = places_by_type["attraction"][sight_idx]
                        days_content += f"**Explore {a.get('name', destination)}**\n"
                        days_content += f"- 🗺️ Visit **{a.get('name')}** — {a.get('description', '')}\n"
                    else:
                        days_content += f"**Free Exploration Day**\n"
                        days_content += f"- 🏙️ Explore {destination} at your own pace\n"
                    if places_by_type["restaurant"]:
                        r = places_by_type["restaurant"][day % len(places_by_type["restaurant"])]
                        days_content += f"- 🍽️ **Dinner**: {r.get('name')} — {r.get('description', '')}\n"
            else:
                # Non-shopping goal: cycle through attractions
                idx = (day - 2) % max(1, len(places_by_type["attraction"]))
                if places_by_type["attraction"]:
                    a = places_by_type["attraction"][idx]
                    days_content += f"**Exploring {a.get('name', destination)}**\n"
                    days_content += f"- 🗺️ Visit **{a.get('name', 'Top Attraction')}** — {a.get('description', '')}\n"
                else:
                    days_content += f"**Day {day} in {destination}**\n"
                    days_content += "- 🏙️ Explore local neighbourhoods\n"
                if places_by_type["restaurant"]:
                    r = places_by_type["restaurant"][day % len(places_by_type["restaurant"])]
                    days_content += f"- 🍽️ **Dinner**: {r.get('name', 'Local Eatery')} — {r.get('description', '')}\n"


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
