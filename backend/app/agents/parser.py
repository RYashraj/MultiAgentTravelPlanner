import json
import logging
import re
from typing import Any, List, Dict
import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

def heuristic_parse(messages: List[Any], destination: str) -> Dict[str, Any]:
    """Fallback parser using regex and keyword matching when Gemini API is unavailable."""
    # Concatenate all user messages to analyze the cumulative state
    full_text_parts = []
    for msg in messages:
        role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else None)
        content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)
        if role == "user" and content:
            full_text_parts.append(content)
            
    full_text = " ".join(full_text_parts).lower()
    
    # 1. Extract Budget
    budget = None
    # Look for currency symbols ($/Rs/₹/€/£) followed by digits, or digits followed by currencies/words
    budget_match = re.search(
        r'(?:[\$\u20B9\u20AC\u00A3]\s*\d+[\d,]*|\d+[\d,]*\s*(?:usd|inr|rs|rupees|euro|euros|pounds|gbp))', 
        full_text
    )
    if budget_match:
        budget = budget_match.group(0).strip()
    elif "budget" in full_text:
        num_match = re.search(r'budget.*?(\d+[\d,]*)', full_text)
        if num_match:
            budget = f"${num_match.group(1)}"
            
    # 2. Extract Duration (Days)
    duration_days = None
    duration_match = re.search(r'(\d+)\s*(?:day|days|night|nights)', full_text)
    if duration_match:
        try:
            duration_days = int(duration_match.group(1))
        except ValueError:
            pass
    elif "one week" in full_text or "a week" in full_text:
        duration_days = 7
    elif "weekend" in full_text:
        duration_days = 2
        
    # 3. Extract Dates / Timing
    dates = None
    months = [
        "january", "february", "march", "april", "may", "june", 
        "july", "august", "september", "october", "november", "december",
        "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec"
    ]
    for m in months:
        if re.search(r'\b' + m + r'\b', full_text):
            dates = m.capitalize()
            break
            
    if not dates:
        if "summer" in full_text:
            dates = "Summer"
        elif "winter" in full_text:
            dates = "Winter"
        elif "spring" in full_text:
            dates = "Spring"
        elif "autumn" in full_text or "fall" in full_text:
            dates = "Autumn"
        elif "next month" in full_text:
            dates = "Next month"
            
    # 4. Extract Preferences
    preferences = []
    keywords = [
        "food", "cuisine", "restaurant", "museum", "history", "culture", 
        "sightseeing", "beach", "nature", "shopping", "adventure", "hiking", 
        "relax", "luxury", "budget", "family", "friends", "solo"
    ]
    for kw in keywords:
        if re.search(r'\b' + kw + r'\b', full_text):
            preferences.append(kw)
            
    # 5. Extract Goal / Purpose
    goal = None
    goal_match = re.search(r'(?:goal|plan|purpose)\s+(?:is|hai|bolato|for)\s+([a-zA-Z\s]+?)(?:\s+and|\s+but|,|\.|$)', full_text)
    if goal_match:
        goal = goal_match.group(1).strip().capitalize()
    else:
        goal_keywords = ["honeymoon", "anniversary", "business", "work", "backpacking", "vacation", "holiday", "relaxation", "explore", "food", "party", "spiritual", "medical", "shopping", "beach", "beaches", "sightseeing", "streetwear", "streetware"]
        for kw in goal_keywords:
            if re.search(r'\b' + kw + r'\b', full_text):
                goal = kw.capitalize()
                break
            
    # 6. Extract Conditions
    conditions = None
    if "vegan" in full_text or "vegetarian" in full_text or "allergies" in full_text or "wheelchair" in full_text or "kids" in full_text or "pets" in full_text:
        # Simple heuristic, just flag that there are special conditions mentioned
        conditions = "User mentioned specific needs (dietary, accessibility, or companions)"

    return {
        "destination": destination,
        "budget": budget,
        "duration_days": duration_days,
        "dates": dates,
        "goal": goal,
        "conditions": conditions,
        "preferences": preferences
    }

async def parse_travel_state(messages: List[Any], destination: str) -> Dict[str, Any]:
    """
    Extracts the travel plan parameters from the chat history.
    Uses the Google Gemini API if configured, otherwise falls back to heuristics.
    """
    settings = get_settings()
    
    # Format chat history text for analysis
    history_lines = []
    for msg in messages:
        role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else None)
        content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)
        if role and content:
            sender = "User" if role == "user" else "Assistant"
            history_lines.append(f"{sender}: {content}")
            
    chat_history_text = "\n".join(history_lines)
    
    if settings.gemini_api_key:
        prompt = (
            f"You are the travel coordinator agent for VoyagerAI.\n"
            f"Your task is to analyze the chat history between the user and the assistant "
            f"for a trip to '{destination}' and extract the current planning parameters.\n\n"
            f"Return ONLY a raw JSON object with the following fields:\n"
            f"- destination: string (default to '{destination}')\n"
            f"- budget: string or null (extract any budget amount, e.g. '$1000', '50000 INR', 'cheap', 'luxury')\n"
            f"- duration_days: integer or null (extract number of days of the trip, e.g. 3, 5, 7)\n"
            f"- dates: string or null (extract travel dates, season, or month, e.g. 'June', 'Dec 1-5', 'any time', 'next month')\n"
            f"- goal: string or null (extract the primary goal, purpose, or main activity of the trip. E.g., 'honeymoon', 'relaxation', 'business', 'shopping', 'beaches'. If the user says 'goal is X' or 'plan is Y', extract that exact value as the goal!)\n"
            f"- conditions: string or null (extract any specific conditions, restrictions or requirements, e.g. 'wheelchair accessible', 'vegan', 'traveling with kids')\n"
            f"- preferences: array of strings (extract secondary user preferences or activities, e.g. ['food', 'museums'])\n\n"
            f"Chat History:\n"
            f"{chat_history_text}"
        )
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={settings.gemini_api_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt
                        }
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json"
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    text_out = data["candidates"][0]["content"]["parts"][0]["text"]
                    parsed = json.loads(text_out)
                    
                    # Basic validation of expected structure
                    return {
                        "destination": parsed.get("destination") or destination,
                        "budget": parsed.get("budget"),
                        "duration_days": parsed.get("duration_days"),
                        "dates": parsed.get("dates"),
                        "goal": parsed.get("goal"),
                        "conditions": parsed.get("conditions"),
                        "preferences": parsed.get("preferences", [])
                    }
                else:
                    logger.warning(f"Gemini API returned status {response.status_code}: {response.text}")
        except Exception as e:
            logger.exception("Failed to call Gemini API for travel state parsing; falling back to heuristics")
            
    # Fallback to heuristics
    return heuristic_parse(messages, destination)
