"""Planner Agent for orchestrating memory retrieval, weather, attractions, and merging."""
import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.attraction_agent import attraction_node
from app.agents.state import AgentState
from app.agents.weather_agent import weather_node
from app.rag.chroma_store import ChromaMemoryStore
from app.core.config import get_settings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)


def retrieve_memory_node(state: AgentState) -> dict[str, Any]:
    """Retrieves relevant past trip context from ChromaMemoryStore."""
    trip_id = state.get("trip_id", "")
    user_message = state.get("user_message", "")

    if not trip_id or not user_message:
        return {"memory_context": []}

    try:
        store = ChromaMemoryStore()
        memory_context = store.retrieve_context(trip_id=trip_id, query=user_message, k=5)
    except Exception as exc:
        logger.error("Error retrieving memory context in retrieve_memory_node: %s", exc, exc_info=True)
        memory_context = []

    return {"memory_context": memory_context}


def merge_node(state: AgentState) -> dict[str, Any]:
    """Uses Gemini to merge outputs from weather, attractions, and memory into a final planner draft."""
    destination = state.get("destination", "")
    dates = state.get("dates")
    budget = state.get("budget")
    preferences = state.get("preferences", [])
    memory_context = state.get("memory_context", [])

    outputs = state.get("agent_outputs") or {}
    weather = outputs.get("weather") or {}
    attractions = outputs.get("attractions") or {}

    weather_summary = weather.get("summary", "")
    weather_warnings = list(weather.get("warnings") or [])

    raw_items = attractions.get("items") or []
    warnings: list[str] = list(weather_warnings)

    is_rainy = any("rain" in str(w).lower() or "storm" in str(w).lower() for w in weather_warnings)
    processed_attractions: list[dict[str, Any]] = []

    for item in raw_items:
        item_copy = dict(item)
        if is_rainy and item_copy.get("outdoor"):
            warning_msg = f"Weather warning ({', '.join(weather_warnings)}): Consider indoor alternative for outdoor attraction '{item_copy.get('name')}'."
            if warning_msg not in warnings:
                warnings.append(warning_msg)
            item_copy["weather_flag"] = "outdoor_rain_risk"
        processed_attractions.append(item_copy)

    try:
        api_key = get_settings().gemini_api_key
        if not api_key:
            raise ValueError("Gemini API key missing")
            
        llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", api_key=api_key)
        sys_msg = SystemMessage(content="You are an expert travel planner. Write a comprehensive, engaging itinerary draft in Markdown.")
        
        user_prompt = f"""
        Destination: {destination}
        Dates: {dates}
        Budget: {budget}
        Preferences: {', '.join(preferences)}
        
        Weather Forecast: {weather_summary}
        Weather Warnings: {', '.join(warnings) if warnings else 'None'}
        
        Suggested Attractions: {processed_attractions}
        
        Past Conversation Memory: {memory_context}
        
        Please draft the final itinerary response. Highlight any weather concerns.
        """
        response = llm.invoke([sys_msg, HumanMessage(content=user_prompt)])
        narrative = str(response.content)
    except Exception as e:
        logger.error(f"Error invoking Gemini in merge_node: {e}")
        attraction_names = [a.get("name", "") for a in processed_attractions if a.get("name")]
        attractions_str = ", ".join(attraction_names) if attraction_names else "No specific attractions found"
        narrative = (
            f"Itinerary Draft for {destination} ({dates or 'Flexible dates'}):\n"
            f"Weather Outlook: {weather_summary or 'Standard forecast'}.\n"
            f"Recommended Attractions ({len(processed_attractions)}): {attractions_str}.\n"
            f"Budget Level: {budget or 'Unspecified'} | Preferences: {', '.join(preferences) if preferences else 'General'}"
        )

    planner_output = {
        "destination": destination,
        "dates": dates,
        "weather_summary": weather_summary,
        "attractions": processed_attractions,
        "warnings": warnings,
        "narrative": narrative,
        "used_memory": memory_context,
    }

    return {"agent_outputs": {**outputs, "planner": planner_output}}


workflow = StateGraph(AgentState)
workflow.add_node("retrieve_memory", retrieve_memory_node)
workflow.add_node("weather", weather_node)
workflow.add_node("attractions", attraction_node)
workflow.add_node("merge", merge_node)

workflow.add_edge(START, "retrieve_memory")
workflow.add_edge("retrieve_memory", "weather")
workflow.add_edge("retrieve_memory", "attractions")
workflow.add_edge("weather", "merge")
workflow.add_edge("attractions", "merge")
workflow.add_edge("merge", END)

planner_graph = workflow.compile()
