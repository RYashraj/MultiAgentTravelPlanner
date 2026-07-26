"""Coordinator Agent: multi-step LangGraph workflow that primes trip context.

Runs four sequential nodes (coordinator → logistics → accommodation → experience),
each making a focused Gemini call to build rich contextual data before the
Planner Agent synthesises the final itinerary.
"""
import logging
import time
import random
import httpx
from langgraph.graph import END, START, StateGraph

from app.agents.state import AgentState
from app.core.config import get_settings

logger = logging.getLogger(__name__)

_GEMINI_MODEL = "gemini-2.0-flash"


def _call_gemini(prompt: str, timeout: float = 20.0) -> str:
    """Synchronous Gemini call for use inside LangGraph sync nodes."""
    settings = get_settings()
    if not settings.gemini_api_key:
        return "Gemini API key not configured — using placeholder data."

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{_GEMINI_MODEL}:generateContent?key={settings.gemini_api_key}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    max_retries = 6
    base_delay = 5.0

    try:
        with httpx.Client(timeout=timeout) as client:
            for attempt in range(max_retries):
                response = client.post(url, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                elif response.status_code == 429 and attempt < max_retries - 1:
                    sleep_time = (base_delay * (2 ** attempt)) + random.uniform(0, 3)
                    logger.warning("Gemini 429 Too Many Requests (attempt %d). Retrying in %.1f seconds...", attempt + 1, sleep_time)
                    time.sleep(sleep_time)
                    continue
                
                logger.warning("Gemini coordinator call returned %s", response.status_code)
                return f"Gemini API error ({response.status_code})."
    except Exception as exc:
        logger.exception("Gemini coordinator call failed")
        return f"Failed to reach Gemini: {exc}"


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

def coordinator_node(state: AgentState) -> dict:
    context = {
        "origin": state.get("origin"),
        "destination": state["destination"],
        "dates": state.get("dates"),
        "budget": state.get("budget"),
        "preferences": state.get("preferences", []),
    }
    response = {
        "status": "planning_started",
        "message": (
            f"Planning has started for {state['destination']}. "
            "Preferences recorded — coordinating research agents now."
        ),
        "trip_context": context,
    }
    return {"agent_outputs": {**state.get("agent_outputs", {}), "coordinator": response}}


def research_node(state: AgentState) -> dict:
    origin = state.get("origin") or "an unspecified origin"
    dest = state["destination"]
    budget = state.get("budget") or "moderate"
    goal = state.get("goal") or "a general trip"
    duration_days = state.get("duration_days") or 3
    prefs = ", ".join(state.get("preferences", [])) or "general sightseeing"

    prompt = (
        f"You are the Research Agent for VoyagerAI. "
        f"The traveller is going from {origin} to {dest} for {duration_days} days with a {budget} budget. "
        f"Their main goal is: {goal}. "
        f"Their interests include: {prefs}. "
        f"Provide a concise, realistic summary covering three areas:\n"
        f"1. Logistics: The best travel options with estimated times and costs.\n"
        f"2. Accommodation: Recommend 3 realistic hotels or neighbourhoods that fit this budget and goal.\n"
        f"3. Experience: List 5 must-do activities, cultural sites, or restaurants tailored to their goal.\n"
        f"Keep it engaging, factual, and well-formatted."
    )
    result = _call_gemini(prompt)
    return {"agent_outputs": {**state.get("agent_outputs", {}), "research": {"result": result}}}


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

_workflow = StateGraph(AgentState)
_workflow.add_node("coordinator", coordinator_node)
_workflow.add_node("research", research_node)

_workflow.add_edge(START, "coordinator")
_workflow.add_edge("coordinator", "research")
_workflow.add_edge("research", END)

coordinator_graph = _workflow.compile()
