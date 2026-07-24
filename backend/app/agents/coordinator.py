"""Week 4 Coordinator: Multi-agent LangGraph workflow with real LLM calls."""
import json
import httpx
from langgraph.graph import END, START, StateGraph

from app.agents.state import AgentState
from app.core.config import get_settings


def _call_gemini(prompt: str) -> str:
    """Helper to call Gemini API synchronously within a graph node."""
    settings = get_settings()
    if not settings.gemini_api_key:
        return "Gemini API key is not configured. Returning mock data."
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={settings.gemini_api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    try:
        # Use sync client since LangGraph nodes here are sync
        with httpx.Client(timeout=15.0) as client:
            response = client.post(url, json=payload)
            if response.status_code == 200:
                data = response.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
            else:
                return f"Error from Gemini API: {response.status_code}"
    except Exception as e:
        return f"Failed to call Gemini API: {str(e)}"


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
        "message": f"Planning has started for {state['destination']}. I recorded your preferences and will coordinate the travel research next.",
        "trip_context": context,
    }
    return {"agent_outputs": {**state.get("agent_outputs", {}), "coordinator": response}}


def logistics_node(state: AgentState) -> dict:
    origin = state.get("origin", "Unknown")
    dest = state["destination"]
    
    prompt = (
        f"You are the Logistics Agent for a travel planner. The user is traveling from {origin} to {dest}. "
        f"Provide a realistic, concise summary of the best travel options (flights, trains, or driving) "
        f"including estimated travel times and rough costs. Keep it brief and factual."
    )
    result = _call_gemini(prompt)
    
    return {"agent_outputs": {**state.get("agent_outputs", {}), "logistics": {"result": result}}}


def accommodation_node(state: AgentState) -> dict:
    dest = state["destination"]
    budget = state.get("budget", "moderate")
    
    prompt = (
        f"You are the Accommodation Agent for a travel planner. The user needs a place to stay in {dest}. "
        f"Their budget/preference is: {budget}. "
        f"Provide 3 realistic hotel or neighborhood recommendations that fit this budget. "
        f"Include a brief description of why it's a good choice."
    )
    result = _call_gemini(prompt)
    
    return {"agent_outputs": {**state.get("agent_outputs", {}), "accommodation": {"result": result}}}


def experience_node(state: AgentState) -> dict:
    dest = state["destination"]
    prefs = ", ".join(state.get("preferences", []))
    
    prompt = (
        f"You are the Experience Agent for a travel planner. The user is visiting {dest}. "
        f"Their preferences/goals include: {prefs if prefs else 'general sightseeing'}. "
        f"Provide a list of 4-5 must-do realistic activities, cultural sites, or restaurants in {dest} "
        f"that match their interests. Keep it engaging but concise."
    )
    result = _call_gemini(prompt)
    
    return {"agent_outputs": {**state.get("agent_outputs", {}), "experience": {"result": result}}}


workflow = StateGraph(AgentState)

workflow.add_node("coordinator", coordinator_node)
workflow.add_node("logistics", logistics_node)
workflow.add_node("accommodation", accommodation_node)
workflow.add_node("experience", experience_node)

workflow.add_edge(START, "coordinator")
workflow.add_edge("coordinator", "logistics")
workflow.add_edge("logistics", "accommodation")
workflow.add_edge("accommodation", "experience")
workflow.add_edge("experience", END)

coordinator_graph = workflow.compile()
