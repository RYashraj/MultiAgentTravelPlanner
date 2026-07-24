"""Planner Agent: retrieves memory, fetches weather + attractions, then merges via Gemini."""
import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.attraction_agent import attraction_node
from app.agents.state import AgentState
from app.agents.weather_agent import weather_node
from app.rag.chroma_store import ChromaMemoryStore
from app.core.config import get_settings
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from app.tools.weather_tool import get_weather
from app.tools.places_tool import search_places
from pydantic import SecretStr

logger = logging.getLogger(__name__)

def retrieve_memory_node(state: AgentState) -> dict[str, Any]:
    """Retrieves relevant past trip context from ChromaMemoryStore."""
    trip_id = state.get("trip_id", "")
    user_message = state.get("user_message", "")

    if not trip_id or not user_message:
        return {"memory_context": []}

    try:
        from app.rag.chroma_store import ChromaMemoryStore
        store = ChromaMemoryStore()
        memory_context = store.retrieve_context(trip_id=trip_id, query=user_message, k=5)
    except Exception as exc:
        logger.error("Error retrieving memory context: %s", exc)
        memory_context = []

    return {"memory_context": memory_context}


def fetch_data_node(state: AgentState) -> dict[str, Any]:
    """Old fetch data node. Now obsolete, as Planner does it. Just passing through."""
    return {}


def merge_node(state: AgentState) -> dict[str, Any]:
    """Uses Gemini with real TOOL CALLING to fetch weather, attractions, and generate itinerary."""
    destination = state.get("destination", "")
    dates = state.get("dates")
    budget = state.get("budget")
    preferences = list(state.get("preferences") or [])
    memory_context = list(state.get("memory_context") or [])
    outputs = state.get("agent_outputs") or {}

    api_key = get_settings().gemini_api_key
    gemini_success = False
    full_narrative = ""

    if api_key:
        try:
            llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                api_key=SecretStr(api_key),
                max_retries=1,
                request_timeout=30,
            )
            # Bind our tools to the LLM
            llm_with_tools = llm.bind_tools([get_weather, search_places])
            
            sys_msg = SystemMessage(
                content=(
                    "You are the VoyagerAI Planner Agent. You MUST use your tools (get_weather, search_places) "
                    "to fetch real-world data about the destination before writing the itinerary. "
                    "Once you have the data, write a detailed, engaging day-by-day itinerary in Markdown format."
                )
            )
            user_prompt = (
                f"Please plan a trip to {destination}.\n"
                f"Dates: {dates}\n"
                f"Budget: {budget}\n"
                f"Preferences: {', '.join(preferences)}\n\n"
                f"Past Context: {memory_context}\n\n"
                "First, call the get_weather tool. Then call the search_places tool to find attractions and hotels. "
                "Finally, use that data to write the day-by-day itinerary."
            )
            
            messages = [sys_msg, HumanMessage(content=user_prompt)]
            
            # Step 1: LLM decides which tools to call
            response = llm_with_tools.invoke(messages)
            messages.append(response)
            
            # Step 2: Execute tool calls if any
            if response.tool_calls:
                logger.info(f"Planner Agent executing {len(response.tool_calls)} tool calls.")
                for tc in response.tool_calls:
                    if tc["name"] == "get_weather":
                        tool_res = get_weather.invoke(tc["args"])
                    elif tc["name"] == "search_places":
                        tool_res = search_places.invoke(tc["args"])
                    else:
                        tool_res = "Unknown tool"
                    
                    messages.append(ToolMessage(content=str(tool_res), tool_call_id=tc["id"]))
                
                # Step 3: LLM generates final itinerary using the tool data
                final_response = llm_with_tools.invoke(messages)
                full_narrative = str(final_response.content) if final_response.content else ""
                gemini_success = True
            else:
                # Fallback if it didn't call tools
                full_narrative = str(response.content) if response.content else ""
                gemini_success = True
                
        except Exception as e:
            logger.warning("Gemini Planner failed (%s). Using fallback.", type(e).__name__)

    if not gemini_success:
        # Fallback to local data
        w_data = get_weather.invoke({"location": destination})
        p_data = search_places.invoke({"location": destination, "query_type": "all"})
        full_narrative = f"# VoyagerAI Itinerary for {destination}\n\n**Weather:** {w_data}\n\n**Places:** {p_data}"

    planner_output = {
        "narrative": full_narrative,
        "gemini_used": gemini_success,
    }

    return {"agent_outputs": {**outputs, "planner": planner_output}}

workflow = StateGraph(AgentState)
workflow.add_node("retrieve_memory", retrieve_memory_node)
workflow.add_node("fetch_data", fetch_data_node)
workflow.add_node("merge", merge_node)

workflow.add_edge(START, "retrieve_memory")
workflow.add_edge("retrieve_memory", "fetch_data")
workflow.add_edge("fetch_data", "merge")
workflow.add_edge("merge", END)

planner_graph = workflow.compile()
