"""
Parser Agent: extracts structured travel parameters from chat history.

Tries Gemini first (JSON mode) — falls back to regex heuristics if unavailable.
"""
import asyncio
import json
import logging
import re
import random
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Heuristic fallback
# ---------------------------------------------------------------------------

def heuristic_parse(messages: list[Any], destination: str) -> dict[str, Any]:
    """Regex/keyword fallback when Gemini is unavailable."""
    parts: list[str] = []
    asked_origin = False
    origin = None

    for msg in messages:
        role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else None)
        content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)
        
        if not content:
            continue
            
        if role == "assistant":
            if "Where will you be travelling from?" in content:
                asked_origin = True
        elif role == "user":
            parts.append(content)
            if asked_origin and len(content.split()) <= 4:
                clean_content = re.sub(r'^(?:i am )?(?:from|traveling from|departing from|leaving from|coming from)\s+', '', content.lower(), flags=re.IGNORECASE)
                origin = clean_content.strip().title()
            asked_origin = False

    text = " ".join(parts).lower()

    # Origin — only match explicit departure phrases, not loose "from"
    # Origin — only match explicit departure phrases, not loose "from" (if not already found contextually)
    if not origin:
        m = re.search(r'\b(?:traveling|departing|flying|leaving|coming)\s+(?:from)\s+([a-zA-Z\s]+?)(?:\s+to\b|\s+for\b|,|\.|$)', text)
        if m:
            candidate = m.group(1).strip()
            if candidate not in ("here", "home", "there", "the"):
                origin = candidate.title()

    # Budget
    budget = None
    m = re.search(r'(?:[\$\u20B9\u20AC\u00A3]\s*\d[\d,]*|\d[\d,]*\s*(?:usd|inr|rs|rupees?|euros?|pounds?|gbp))', text)
    if m:
        budget = m.group(0).strip()
    elif re.search(r'\b(?:no limit|unlimited|luxury)\b', text):
        budget = "Luxury / No limit"
    elif re.search(r'\b(?:budget.friendly|cheap|low.cost)\b', text):
        budget = "Budget-friendly"
    else:
        m = re.search(r'budget.*?(\d[\d,]+)', text)
        if m:
            budget = f"${m.group(1)}"

    # Duration
    duration_days = None
    m = re.search(r'(\d+)\s*(?:day|night)s?', text)
    if m:
        try:
            duration_days = int(m.group(1))
        except ValueError:
            pass
    elif re.search(r'\b(?:one week|a week)\b', text):
        duration_days = 7
    elif "weekend" in text:
        duration_days = 2

    # Dates / season
    dates = None
    months = [
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
        "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    ]
    for mon in months:
        if re.search(r'\b' + mon + r'\b', text):
            dates = mon.capitalize()
            break
    if not dates:
        for season, label in [("summer", "Summer"), ("winter", "Winter"), ("spring", "Spring"), ("autumn", "Autumn"), ("fall", "Autumn")]:
            if season in text:
                dates = label
                break
    if not dates and "next month" in text:
        dates = "Next month"

    # Preferences
    preference_keywords = [
        "food", "cuisine", "restaurant", "museum", "history", "culture",
        "sightseeing", "beach", "nature", "shopping", "adventure", "hiking",
        "relax", "luxury", "budget", "family", "friends", "solo",
    ]
    preferences = [kw for kw in preference_keywords if re.search(r'\b' + kw + r'\b', text)]

    # Goal
    goal = None
    goal_keywords = [
        "honeymoon", "anniversary", "business", "work", "backpacking",
        "vacation", "holiday", "relaxation", "explore", "food", "party",
        "spiritual", "medical", "shopping", "beach", "sightseeing",
    ]
    for kw in goal_keywords:
        if re.search(r'\b' + kw + r'\b', text):
            goal = kw.capitalize()
            break

    # Conditions
    conditions = None
    if re.search(r'\b(?:vegan|vegetarian|allergies|wheelchair|kids|children|pets)\b', text):
        conditions = "User mentioned specific needs"

    return {
        "origin": origin,
        "destination": destination,
        "budget": budget,
        "duration_days": duration_days,
        "dates": dates,
        "goal": goal,
        "conditions": conditions,
        "preferences": preferences,
    }


# ---------------------------------------------------------------------------
# Gemini-powered extraction
# ---------------------------------------------------------------------------

async def parse_travel_state(messages: list[Any], destination: str) -> dict[str, Any]:
    """
    Extract travel-plan parameters from chat history.
    Uses Gemini JSON mode when configured; falls back to heuristics.
    """
    settings = get_settings()

    history_lines: list[str] = []
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
            f"Analyze the chat history for a trip to '{destination}' and extract planning parameters.\n\n"
            f"CRITICAL: Do NOT guess or hallucinate. If a value is not explicitly stated, set it to null.\n\n"
            f"Return ONLY a raw JSON object with these fields:\n"
            f"- origin: string or null (city the user departs from)\n"
            f"- destination: string (default: '{destination}')\n"
            f"- budget: string or null (e.g. '$1000', '50000 INR', 'luxury', 'no limit')\n"
            f"- duration_days: integer or null (number of trip days)\n"
            f"- dates: string or null (travel month, season, or date range)\n"
            f"- goal: string or null (primary trip purpose: honeymoon, relaxation, business, etc.)\n"
            f"- conditions: string or null (dietary, accessibility, or companion requirements)\n"
            f"- preferences: array of strings (secondary interests)\n\n"
            f"Chat History:\n{chat_history_text}"
        )

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={settings.gemini_api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }

        max_retries = 6
        base_delay = 5.0

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                for attempt in range(max_retries):
                    response = await client.post(url, json=payload)
                    if response.status_code == 200:
                        data = response.json()
                        text_out = data["candidates"][0]["content"]["parts"][0]["text"]
                        parsed = json.loads(text_out)
                        return {
                            "origin": parsed.get("origin"),
                            "destination": parsed.get("destination") or destination,
                            "budget": parsed.get("budget"),
                            "duration_days": parsed.get("duration_days"),
                            "dates": parsed.get("dates"),
                            "goal": parsed.get("goal"),
                            "conditions": parsed.get("conditions"),
                            "preferences": parsed.get("preferences") or [],
                        }
                    elif response.status_code == 429 and attempt < max_retries - 1:
                        sleep_time = (base_delay * (2 ** attempt)) + random.uniform(0, 3)
                        logger.warning("Gemini 429 (attempt %d). Retrying in %.1f seconds...", attempt + 1, sleep_time)
                        await asyncio.sleep(sleep_time)
                        continue
                    
                    logger.warning("Gemini returned status %s for parse_travel_state", response.status_code)
                    break
        except Exception:
            logger.exception("Gemini parse_travel_state failed — using heuristics")

    return heuristic_parse(messages, destination)
