"""Coordinator Agent: multi-step LangGraph workflow that primes trip context.

FIXED: No longer makes Gemini API calls. Uses local logic only to avoid 429 rate
limits and long wait times. The Planner Agent makes the single Gemini call.
"""
import logging

from langgraph.graph import END, START, StateGraph

from app.agents.state import AgentState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Graph nodes — no Gemini calls here (rate limit fix)
# ---------------------------------------------------------------------------

def coordinator_node(state: AgentState) -> dict:
    """Records trip context — no external API calls."""
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
    """Builds research context locally — no external API calls (rate limit fix)."""
    origin = state.get("origin") or "your origin"
    dest = state["destination"]
    budget = state.get("budget") or "moderate"
    goal = state.get("goal") or "a general trip"
    duration_days = state.get("duration_days") or 3
    prefs = ", ".join(state.get("preferences", [])) or "general sightseeing"

    # Build a rich local context that the Planner Agent will use
    result = (
        f"Research context for {dest} trip:\n"
        f"- Traveller from: {origin}\n"
        f"- Duration: {duration_days} days\n"
        f"- Budget: {budget}\n"
        f"- Goal: {goal}\n"
        f"- Interests: {prefs}\n"
        f"Use this context to generate a detailed, personalised itinerary."
    )
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
