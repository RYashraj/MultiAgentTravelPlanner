"""
Planner Agent: retrieves RAG memory context, then synthesises a full itinerary
using Gemini 2.0 Flash with real tool calls (weather + places).

Graph: START → retrieve_memory → merge → END
"""
import json
import logging
from functools import lru_cache
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph
from pydantic import SecretStr

from app.agents.state import AgentState
from app.core.config import get_settings
from app.tools.places_tool import search_places
from app.tools.weather_tool import get_weather

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Singleton ChromaDB store — opened once per process, not per request
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

    # Pull coordinator context (research) into the prompt
    research_info = outputs.get("research", {}).get("result", "")

    api_key = get_settings().gemini_api_key
    gemini_success = False
    full_narrative = ""

    if api_key:
        try:
            llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                api_key=SecretStr(api_key),
                max_retries=6,
                timeout=30,
            )
            llm_with_tools = llm.bind_tools([get_weather, search_places])

            coordinator_context = ""
            if research_info:
                coordinator_context += f"\n**Research Context:**\n{research_info}\n"

            sys_msg = SystemMessage(
                content=(
                    "You are the VoyagerAI Planner Agent. "
                    "You MUST call get_weather and search_places tools to fetch live data before writing the itinerary. "
                    "Once you have the data, write a detailed, engaging day-by-day itinerary in Markdown. "
                    "Use rich formatting: bold section headers, bullet points, emojis where appropriate. "
                    "The itinerary should feel like it was written by a professional travel curator."
                )
            )
            user_prompt = (
                f"Plan a trip to **{destination}** from **{origin or 'unspecified origin'}**.\n"
                f"- Duration: {duration_days} days\n"
                f"- Goal: {goal or 'general travel'}\n"
                f"- Dates/Season: {dates or 'flexible'}\n"
                f"- Budget: {budget or 'not specified'}\n"
                f"- Preferences: {', '.join(preferences) or 'general sightseeing'}\n"
                f"- Past context: {memory_context or 'None'}\n"
                f"{coordinator_context}\n"
                "Steps:\n"
                "1. Call get_weather to check the forecast.\n"
                "2. Call search_places with query_type='all' to find attractions, restaurants, and hotels.\n"
                "3. Write a polished day-by-day itinerary using all gathered data."
            )

            messages: list[BaseMessage] = [sys_msg, HumanMessage(content=user_prompt)]

            # Step 1: LLM decides which tools to call
            response = llm_with_tools.invoke(messages)
            messages.append(response)

            # Step 2: Execute tool calls
            if response.tool_calls:
                logger.info("Planner: executing %d tool calls", len(response.tool_calls))
                for tc in response.tool_calls:
                    if tc["name"] == "get_weather":
                        tool_res = get_weather.invoke(tc["args"])
                    elif tc["name"] == "search_places":
                        tool_res = search_places.invoke(tc["args"])
                    else:
                        tool_res = "Unknown tool"
                    messages.append(ToolMessage(content=str(tool_res), tool_call_id=tc["id"]))

            # Step 3: Final synthesis — use bare llm (no tools) to prevent looping
            final_response = llm.invoke(messages)
            full_narrative = str(final_response.content) if final_response.content else ""
            gemini_success = True

        except Exception:
            logger.warning("Gemini Planner failed — using local fallback", exc_info=True)

    if not gemini_success:
        # Local fallback using mock tools directly
        w_data_raw = get_weather.invoke({"location": destination})
        p_data_raw = search_places.invoke({"location": destination, "query_type": "all"})
        
        try:
            w_data = json.loads(w_data_raw) if isinstance(w_data_raw, str) else w_data_raw
        except Exception:
            w_data = w_data_raw
            
        try:
            p_data = json.loads(p_data_raw) if isinstance(p_data_raw, str) else p_data_raw
        except Exception:
            p_data = p_data_raw
        
        # Format weather nicely
        if isinstance(w_data, dict):
            w_str = f"{w_data.get('temp', 'N/A')} — {w_data.get('condition', 'N/A')}. {w_data.get('forecast', '')}"
        else:
            w_str = str(w_data)
            
        # Format places nicely
        p_str = ""
        if isinstance(p_data, list):
            for p in p_data:
                p_str += f"- **{p.get('name', 'Unknown')}** ({p.get('type', 'place')}): {p.get('description', '')}\n"
        else:
            p_str = str(p_data)
            
        full_narrative = (
            f"# VoyagerAI Itinerary for {destination}\n\n"
            f"*(Note: AI planning unavailable due to limits — showing local data for your {duration_days}-day '{goal or 'trip'}' from {origin or 'unspecified'})*\n\n"
            f"**Weather:** {w_str}\n\n"
            f"**Places & Attractions:**\n{p_str}\n"
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
