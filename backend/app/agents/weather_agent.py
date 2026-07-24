"""Weather Agent for Travel Planner."""
import logging
from typing import Any

from app.agents.state import AgentState
from app.tools.weather_tool import get_weather

logger = logging.getLogger(__name__)


def weather_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node function for fetching weather forecast."""
    destination = state.get("destination", "")
    dates = state.get("dates")

    try:
        import json
        data_str = get_weather(destination)
        data = json.loads(data_str)
        forecast = data.get("forecast", data) if isinstance(data, dict) else data
        condition = data.get("condition", "") if isinstance(data, dict) else ""
        temperature = data.get("temperature", "") if isinstance(data, dict) else ""

        if condition and temperature:
            summary = f"Weather for {destination}: {condition}, {temperature}."
        elif isinstance(forecast, str) and forecast:
            summary = f"Weather for {destination}: {forecast}"
        else:
            summary = f"Weather forecast retrieved for {destination}."

        warnings: list[str] = data.get("warnings", []) if isinstance(data, dict) else []
        if isinstance(condition, str) and ("rain" in condition.lower() or "storm" in condition.lower()):
            if "heavy rain" not in warnings:
                warnings.append("heavy rain")

        is_estimate = data.get("is_estimate", False) if isinstance(data, dict) else False
        
        weather_output = {
            "forecast": forecast,
            "summary": summary,
            "warnings": warnings,
            "is_estimate": is_estimate,
        }
    except Exception as exc:
        logger.error("Error running weather tool for destination '%s': %s", destination, exc, exc_info=True)
        weather_output = {
            "forecast": {},
            "summary": f"Unable to fetch weather for {destination}.",
            "warnings": [],
        }

    existing_outputs = dict(state.get("agent_outputs") or {})
    return {"agent_outputs": {**existing_outputs, "weather": weather_output}}
