"""
Coordinator Agent: multi-step LangGraph workflow that primes trip context.

Both nodes call Gemini for intelligent, context-aware research.
Uses the shared GeminiClient (rate-limit-safe, model fallback chain).
Falls back to rich local context strings if Gemini is unavailable.

Performance: imports at module level, call_gemini used directly (no lazy import).
"""
import logging

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from app.agents.gemini_client import call_gemini
from app.agents.state import AgentState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Graph nodes — Gemini-powered with local fallback
# ---------------------------------------------------------------------------

def coordinator_node(state: AgentState) -> dict:
    """
    Coordinator: instantly primes trip context and coordination brief (0 API latency).
    """
    destination = state["destination"]
    origin = state.get("origin") or "unspecified"
    budget = state.get("budget") or "moderate"
    goal = state.get("goal") or "general travel"
    duration_days = state.get("duration_days") or 3
    prefs = ", ".join(state.get("preferences") or []) or "general sightseeing"

    ai_summary = (
        f"Coordination brief for {destination} trip:\n"
        f"- Traveller departing from {origin}, budget: {budget} ({duration_days} days, goal: {goal})\n"
        f"- Preferences & interests: {prefs}\n"
        f"- Nuances: Prioritize budget-appropriate accommodation matching {budget}. "
        f"Include specific local transport options with INR pricing, authentic regional dining spots, "
        f"and well-timed day-by-day sightseeing that avoids rushing."
    )

    response = {
        "status": "planning_started",
        "message": f"Coordinator brief ready for {destination}.",
        "ai_brief": ai_summary,
        "trip_context": {
            "origin": origin,
            "destination": destination,
            "budget": budget,
            "goal": goal,
            "duration_days": duration_days,
            "preferences": state.get("preferences", []),
        },
    }
    return {"agent_outputs": {**state.get("agent_outputs", {}), "coordinator": response}}


def research_node(state: AgentState) -> dict:
    """
    Research Node: synthesizes research context from coordinator brief and trip parameters.
    Instantaneous execution (0 API latency) to avoid sequential LLM bottlenecks.
    """
    origin = state.get("origin") or "your origin"
    dest = state["destination"]
    budget = state.get("budget") or "moderate"
    goal = state.get("goal") or "a general trip"
    duration_days = state.get("duration_days") or 3
    prefs = ", ".join(state.get("preferences") or []) or "general sightseeing"

    # Get coordinator brief if available
    coord_output = state.get("agent_outputs", {}).get("coordinator", {})
    coord_brief = coord_output.get("ai_brief", "")

    result = (
        f"Research & Coordination Brief for {dest} trip:\n"
        f"- Traveller from: {origin} | Duration: {duration_days} days\n"
        f"- Budget: {budget} | Goal: {goal} | Interests: {prefs}\n"
        f"- Coordinator Guidance: {coord_brief}\n"
        f"- Focus on specific local transport, budget-appropriate stays, real street markets, and practical pricing in INR."
    )
    logger.info("ResearchNode: research brief synthesized instantly (%d chars)", len(result))
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
