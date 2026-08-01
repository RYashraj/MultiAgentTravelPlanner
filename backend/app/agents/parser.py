"""
Parser Agent: extracts structured travel parameters from chat history.

Tries Gemini first (JSON mode) — falls back to regex heuristics if unavailable.
"""
import json
import logging
import re
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
    origin = None

    for msg in messages:
        role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else None)
        content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)

        if not content:
            continue

        if role == "user":
            parts.append(content)
            # Always scan every user message for origin patterns
            # Pattern: short reply after agent asked 'where from' — e.g. 'Gujarat' or 'from Gujarat'
            stripped = re.sub(
                r'^(?:i am |i\'m )?(?:from|traveling from|travelling from|departing from|leaving from|coming from)\s+',
                '', content.lower(), flags=re.IGNORECASE
            ).strip().title()
            # Accept as standalone origin reply if it's short (1-3 words) and not a full sentence
            if stripped and len(content.split()) <= 5 and stripped not in ("Here", "Home", "There", "The", "A"):
                if not origin:
                    origin = stripped

    text = " ".join(parts).lower()

    # Origin — match British AND American spelling, plus 'I'm from X', 'from Gujarat', 'travel from X to Y'
    if not origin:
        # Pattern 1: travelling/traveling/travel/flying/leaving/coming from X
        m = re.search(
            r'\b(?:travellin?g|travel|departing|flying|leaving|coming)\s+from\s+([a-zA-Z][a-zA-Z\s]{1,30}?)(?:\s+to\b|\s+for\b|,|\.|$)',
            text
        )
        if m:
            candidate = m.group(1).strip()
            if candidate not in ("here", "home", "there", "the", "a"):
                origin = candidate.title()

    if not origin:
        # Pattern 2: 'I'm from X' or 'I am from X'
        m = re.search(r"\bi(?:'?m| am)\s+from\s+([a-zA-Z][a-zA-Z\s]{1,20}?)(?:\s+to\b|\s+for\b|,|\.|$)", text)
        if m:
            candidate = m.group(1).strip()
            if candidate not in ("here", "home", "there", "the"):
                origin = candidate.title()

    if not origin:
        # Pattern 3: 'from Gujarat/Delhi/...' anywhere in sentence
        m = re.search(r'\bfrom\s+([A-Za-z][a-z]+(?:\s+[A-Z][a-z]+)?)\b', text)
        if m:
            candidate = m.group(1).strip()
            stop_words = {"here", "home", "there", "the", "a", "an", "my", "your", "our", "their", "its"}
            if candidate.lower() not in stop_words and len(candidate) > 2:
                origin = candidate.title()

    # Destination override — if user explicitly said 'to Dwarka', 'visiting Dwarka', 'trip to Dwarka'
    dest_match = re.search(
        r'\b(?:from\s+[a-zA-Z\s]{2,30}?\s+to|travel\s+to|travelling\s+to|traveling\s+to|trip\s+to|visiting|go\s+to|going\s+to)\s+([a-zA-Z][a-zA-Z\s]{1,25}?)(?:\s+for\b|\s+with\b|\s+in\b|\s+on\b|,|\.|$)',
        text,
        re.IGNORECASE,
    )
    if dest_match:
        candidate_dest = dest_match.group(1).strip().title()
        stop_words_dest = {"Here", "Home", "There", "The", "A", "An", "My", "Your", "Our", "Their"}
        if candidate_dest not in stop_words_dest and len(candidate_dest) > 2:
            destination = candidate_dest

    # Budget
    budget = None
    m = re.search(r'(?:[\$\u20B9\u20AC\u00A3]\s*\d[\d,]*|\d[\d,]*\s*(?:usd|inr|rs|rupees?|euros?|pounds?|gbp))', text)
    if m:
        budget = m.group(0).strip()
    elif re.search(r'\b(?:no limit|unlimited)\b', text):
        budget = "Luxury / No limit"
    elif re.search(r'\b(?:luxury|5[- ]?star|five[- ]?star)\b', text):
        budget = "Luxury"
    elif re.search(r'\b(?:budget[- ]friendly|cheap|low[- ]cost|backpack|hostel)\b', text) or re.search(r'\bbudget\b', text):
        budget = "Budget-friendly"
    elif re.search(r'\b(?:mid[- ]?range|moderate|standard)\b', text):
        budget = "Mid-range"
    else:
        m = re.search(r'budget.*?(\d[\d,]+)', text)
        if m:
            budget = f"₹{m.group(1)}"

    # Duration — handle ranges like '7 to 10 days', '7-10 days'
    duration_days = None
    # Range: '7 to 10 days' → take average
    m = re.search(r'(\d+)\s*(?:to|-|–)\s*(\d+)\s*(?:day|night)s?', text)
    if m:
        try:
            duration_days = (int(m.group(1)) + int(m.group(2))) // 2
        except ValueError:
            pass
    if not duration_days:
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
        "sightseeing", "beach", "nature", "shopping", "streetwear", "adventure", "hiking",
        "relax", "luxury", "budget", "family", "friends", "solo",
    ]
    preferences = [kw for kw in preference_keywords if re.search(r'\b' + kw + r'\b', text)]

    # Goal — check explicit phrase 'goal is ...' first
    goal = None
    m_goal = re.search(r'\b(?:my\s+)?(?:goal|purpose|aim|interest|want\s+to\s+do|for)\s*(?:is|are|:)?\s+([a-zA-Z0-9\s,&\+]{3,40}?)(?:\.|$|\n)', text, re.IGNORECASE)
    if m_goal:
        candidate_goal = m_goal.group(1).strip()
        if len(candidate_goal) > 2 and candidate_goal.lower() not in ("a", "the", "my", "this", "trip", "travel"):
            goal = candidate_goal.title()

    if not goal:
        multi_word_goals = [
            ("streetwear shopping", "Streetwear Shopping"),
            ("street shopping", "Street Shopping"),
            ("street food", "Street Food"),
            ("food tour", "Food Tour"),
            ("beaches and adventure", "Beaches and Adventure"),
            ("beach and adventure", "Beaches and Adventure"),
        ]
        for phrase, label in multi_word_goals:
            if phrase in text:
                goal = label
                break

    if not goal:
        goal_keywords = [
            ("adventure", "Adventure"),
            ("beach", "Beaches"),
            ("temple", "Temples & Pilgrimage"),
            ("pilgrim", "Temples & Pilgrimage"),
            ("honeymoon", "Honeymoon"),
            ("anniversary", "Anniversary"),
            ("business", "Business"),
            ("work", "Work"),
            ("backpack", "Backpacking"),
            ("vacation", "Vacation"),
            ("holiday", "Holiday"),
            ("relax", "Relaxation"),
            ("explore", "Exploration"),
            ("sightseeing", "Sightseeing"),
            ("shop", "Shopping"),
            ("spiritual", "Spiritual"),
            ("nature", "Nature & Wildlife"),
            ("wildlife", "Nature & Wildlife"),
            ("food", "Food Tour"),
            ("party", "Nightlife & Party"),
            ("nightlife", "Nightlife & Party"),
        ]
        for kw, label in goal_keywords:
            if kw in text:
                goal = label
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

    # Always try heuristics first — zero API calls, instant result
    heuristic = heuristic_parse(messages, destination)
    
    # If heuristics found any of the core params, trust it (no Gemini call — saves rate limits)
    heuristic_score = sum([
        bool(heuristic.get("origin")),
        bool(heuristic.get("budget")),
        bool(heuristic.get("duration_days")),
        bool(heuristic.get("goal")),
    ])
    if heuristic_score >= 1:
        return heuristic

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
            f"gemini-3.5-flash:generateContent?key={settings.gemini_api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    text_out = data["candidates"][0]["content"]["parts"][0]["text"]
                    parsed = json.loads(text_out)
                    return {
                        "origin": parsed.get("origin") or heuristic.get("origin"),
                        "destination": parsed.get("destination") or destination,
                        "budget": parsed.get("budget") or heuristic.get("budget"),
                        "duration_days": parsed.get("duration_days") or heuristic.get("duration_days"),
                        "dates": parsed.get("dates") or heuristic.get("dates"),
                        "goal": parsed.get("goal") or heuristic.get("goal"),
                        "conditions": parsed.get("conditions") or heuristic.get("conditions"),
                        "preferences": parsed.get("preferences") or heuristic.get("preferences") or [],
                    }
                else:
                    logger.warning("Gemini returned status %s for parse_travel_state — falling back to heuristics", response.status_code)
        except Exception:
            logger.exception("Gemini parse_travel_state failed — using heuristics")

    return heuristic
