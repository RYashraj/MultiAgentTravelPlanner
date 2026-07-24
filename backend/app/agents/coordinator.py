"""Week 3 Coordinator: a minimal, real LangGraph workflow.

The graph deliberately has one node. Week 4 will add Logistics,
Accommodation, and Experience nodes to the same shared state contract.
"""
from langgraph.graph import END, START, StateGraph

from app.agents.state import AgentState


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
