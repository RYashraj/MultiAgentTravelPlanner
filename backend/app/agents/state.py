"""Shared LangGraph state definition for Travel Planner agents."""
from typing import Annotated, TypedDict

def merge_agent_outputs(left: dict[str, dict] | None, right: dict[str, dict] | None) -> dict[str, dict]:
    """Reducer function to safely merge agent outputs across parallel LangGraph nodes."""
    res = dict(left or {})
    if right:
        res.update(right)
    return res


class AgentState(TypedDict):
    trip_id: str
    origin: str | None
    destination: str
    dates: str | None
    budget: str | None
    goal: str | None
    duration_days: int | None
    preferences: list[str]
    user_message: str
    memory_context: list[str]
    agent_outputs: Annotated[dict[str, dict], merge_agent_outputs]
