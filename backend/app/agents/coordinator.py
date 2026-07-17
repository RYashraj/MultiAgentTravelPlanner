"""Week 3 Coordinator: a minimal, real LangGraph workflow.

The graph deliberately has one node. Week 4 will add Logistics,
Accommodation, and Experience nodes to the same shared state contract.
"""
import logging
from typing import TypedDict

# Attempt to load native StateGraph, fallback to compat layer if imports fail due to DLL policies
try:
    from langgraph.graph import StateGraph, START, END
except (ImportError, Exception):
    from app.agents.langgraph_compat import StateGraph, START, END

logger = logging.getLogger(__name__)

class AgentState(TypedDict):
    destination: str
    dates: str | None
    budget: str | None
    preferences: list[str]
    user_message: str
    agent_outputs: dict[str, dict]


def coordinator_node(state: AgentState) -> dict:
    context = {
        "destination": state["destination"],
        "dates": state.get("dates"),
        "budget": state.get("budget"),
        "preferences": state.get("preferences", []),
    }
    response = {
        "status": "planning_started",
        "message": f"Planning has started for {state['destination']}. I recorded your preferences and will coordinate the travel research next.",
        "trip_context": context,
    }
    return {"agent_outputs": {**state.get("agent_outputs", {}), "coordinator": response}}


workflow = StateGraph(AgentState)
workflow.add_node("coordinator", coordinator_node)
workflow.add_edge(START, "coordinator")
workflow.add_edge("coordinator", END)
coordinator_graph = workflow.compile()
