import logging
from typing import TypedDict, List, Dict, Any, Optional

# Attempt to load native StateGraph, fallback to compat layer if imports fail
try:
    from langgraph.graph import StateGraph, START, END
except (ImportError, Exception):
    from app.agents.langgraph_compat import StateGraph, START, END

logger = logging.getLogger(__name__)

class AgentState(TypedDict):
    destination: str
    dates: Optional[str]
    budget: Optional[str]
    preferences: Optional[str]
    agent_outputs: List[Dict[str, Any]]
    messages: List[Dict[str, Any]]

def coordinator_node(state: AgentState) -> Dict[str, Any]:
    """
    Coordinator Agent Node: Echoes back a structured planning started response.
    """
    destination = state.get("destination", "your destination")
    logger.info(f"[Coordinator Graph Node] Running node logic for {destination}")
    
    outputs = list(state.get("agent_outputs") or [])
    outputs.append({
        "agent": "Coordinator Agent",
        "content": f"[Coordinator] Planning started for destination: {destination}. Defining routing schema."
    })
    
    return {
        "agent_outputs": outputs
    }

# Build graph
workflow = StateGraph(AgentState)
workflow.add_node("coordinator", coordinator_node)
workflow.add_edge(START, "coordinator")
workflow.add_edge("coordinator", END)

# Compile graph
coordinator_graph = workflow.compile()
