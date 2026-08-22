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
                model="gemini-2.0-flash",
                api_key=SecretStr(api_key),
                max_retries=1,
                timeout=30,
            )
            llm_with_tools = llm.bind_tools([get_weather, search_places])  # type: ignore[arg-type]

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

RULE 5 - USER PREFERENCES & FOCUS:
- The user's explicitly requested focus/preferences are: {', '.join(preferences) if preferences else 'local exploration'}.
- If the user specifically asked for local markets, beaches, or food, make sure the day-by-day activities revolve around those requested interests!

RULE 6 - FORMAT: Write a beautiful Markdown itinerary with emojis, bold headers, day-by-day breakdown.

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

            full_narrative = call_gemini(messages, timeout=20)
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

        # Check if user requested market/beach focus
        has_market_pref = any("market" in str(p).lower() or "shop" in str(p).lower() for p in preferences)
        has_beach_pref = any("beach" in str(p).lower() for p in preferences)

        # Build day-by-day content
        days_content = ""
        # Tracks how many restaurant picks we've made so far so each pick
        # advances through the list — guarantees no repeat until every
        # restaurant has been used once (instead of the day-branches each
        # computing their own index formula, which routinely collided and
        # kept re-picking the same restaurant on multiple days).
        restaurant_counter = 0

        def next_restaurant():
            nonlocal restaurant_counter
            restaurants = places_by_type["restaurant"]
            if not restaurants:
                return None
            r = restaurants[restaurant_counter % len(restaurants)]
            restaurant_counter += 1
            return r

        for day in range(1, duration_days + 1):
            days_content += f"\n## 🗓️ Day {day}\n"
            if day == 1:
                days_content += "**Arrival & Orientation**\n"
                days_content += f"- ✈️ Arrive in {destination} and check into your accommodation\n"
                if places_by_type["hotel"]:
                    h = places_by_type["hotel"][0]
                    days_content += f"- 🏨 **Recommended Stay**: {h.get('name', 'Local Hotel')} — {h.get('description', '')}\n"
                days_content += "- 🌆 Evening: Explore the local neighbourhood\n"
                r = next_restaurant()
                if r:
                    days_content += f"- 🍽️ **Dinner**: {r.get('name', 'Local Restaurant')} — {r.get('description', '')}\n"
            elif (day == 2 or (has_market_pref and day in (3, 4, 6))) and places_by_type["shopping"]:
                s_idx = (day - 2) % len(places_by_type["shopping"])
                s_item = places_by_type["shopping"][s_idx]
                days_content += f"**{s_item.get('name', 'Local Market')} & Street Shopping**\n"
                days_content += "- 🚶 Morning: Local breakfast and street food exploration\n"
                days_content += f"- 🛍️ **{s_item.get('name')}** — {s_item.get('description', '')}\n"
                days_content += "- 🛍️ Bargain for souvenirs, clothing, spices, and local handicrafts\n"
                r = next_restaurant()
                if r:
                    days_content += f"- 🍽️ **Meal**: {r.get('name')} — {r.get('description', '')}\n"
            elif (has_beach_pref and day in (3, 5, 7)) or (not has_market_pref and day <= len(places_by_type["attraction"]) + 2):
                idx = (day - 2) % max(1, len(places_by_type["attraction"]))
                if places_by_type["attraction"]:
                    a = places_by_type["attraction"][idx]
                    days_content += f"**Exploring {a.get('name', destination)}**\n"
                    days_content += f"- 🗺️ Visit **{a.get('name', 'Top Spot')}** — {a.get('description', '')}\n"
                else:
                    days_content += f"**Scenic Beach & Waterfront Promenade Walk**\n"
                    days_content += f"- 🏖️ Morning & Afternoon: Relax at local beaches, try water activities, and enjoy beach shacks\n"
                days_content += "- 🚶 Morning walk and local breakfast\n"
                r = next_restaurant()
                if r:
                    days_content += f"- 🍽️ **Eatery**: {r.get('name', 'Local Eatery')} — {r.get('description', '')}\n"
            else:
                themes = [
                    ("Cultural Immersion & Neighborhood Walking", "- 🏛️ Morning: Visit local heritage sites and historic plazas\n- ☕ Afternoon: Relax at a traditional café and enjoy regional pastries\n- 🎭 Evening: Experience local evening performances or cultural walk\n"),
                    ("Local Artisan Workshops & Shopping", "- 🎨 Morning: Explore local artisan workshops and craft boutiques\n- 🛍️ Afternoon: Discover hidden alleyways and specialty stores\n- 🍲 Evening: Authentic dinner at a neighborhood favorite restaurant\n"),
                    ("Parks, Gardens & Outdoor Leisure", "- 🌿 Morning: Stroll through scenic botanical gardens and urban parks\n- 🚴 Afternoon: Leisurely bike ride or waterfront promenade walk\n- 🌅 Evening: Sunset drinks and local street snacks\n"),
                    ("Scenic Viewpoints & Architectural Marvels", "- 🏙️ Morning: Visit iconic observation decks and architectural landmarks\n- 📸 Afternoon: Photography tour of famous city vistas\n- 🍽️ Evening: Dinner with a view\n"),
                    ("Gastronomy & Local Food Tasting", "- 🍜 Morning: Local breakfast and food market exploration\n- 🍡 Afternoon: Regional dessert and snack tasting tour\n- 🥂 Evening: Specialty culinary dining experience\n"),
                    ("Day Trip & Surrounding Nature", "- 🚌 Morning: Short excursion to nearby countryside or scenic lookout\n- ⛰️ Afternoon: Nature walk or historic landmark visit\n- 🌌 Evening: Return to city for relaxed dinner\n"),
                    ("Hidden Gems & Bookshops", "- 📚 Morning: Discover quiet historic bookshops and secret courtyards\n- ☕ Afternoon: Specialty coffee tasting and neighborhood lounge\n- 🌃 Evening: Evening stroll and street music\n"),
                    ("Souvenir Hunting & Farewell Celebration", "- 🎁 Morning: Collect authentic local souvenirs and gifts\n- 🛍️ Afternoon: Final shopping spree at top district markets\n- 🍷 Evening: Special farewell dinner celebrating your trip!\n"),
                ]
                theme_idx = (day - 1) % len(themes)
                t_title, t_body = themes[theme_idx]
                days_content += f"**{t_title}**\n{t_body}"

        # Build shopping section
        shopping_section = ""
        if places_by_type["shopping"]:
            shopping_section = "\n## 🛍️ Shopping Hotspots\n"
            for s in places_by_type["shopping"]:
                shopping_section += f"- **{s.get('name')}** — {s.get('description', '')}\n"

        intl_keywords = ["tokyo", "japan", "paris", "france", "london", "uk", "united kingdom", "new york", "usa", "bali", "indonesia", "singapore", "dubai", "uae", "bangkok", "thailand", "rome", "italy", "barcelona", "spain", "sydney", "australia"]
        is_intl = any(k in destination.lower() for k in intl_keywords)
        if is_intl:
            sim_tip = "- 🌐 Get an eSIM or international roaming package for data connectivity"
            booking_tip = "- 🎟️ Book flights on Google Flights / Skyscanner | Check local rail/subway passes"
        else:
            sim_tip = "- 🌐 Get a local SIM card (Jio/Airtel) for data connectivity"
            booking_tip = "- 🎟️ Book trains on IRCTC.co.in | Flights on MakeMyTrip/Goibibo"

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
            f"{sim_tip}\n"
            f"{booking_tip}\n"
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
