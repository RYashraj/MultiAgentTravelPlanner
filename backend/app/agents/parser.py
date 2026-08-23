"""
Parser Agent: extracts structured travel parameters from chat history.

Tries Gemini first (JSON mode via shared gemini_client) — falls back to regex heuristics.
Using the shared client ensures rate limiting, model fallback, and retry logic are applied.
"""
import json
import logging
import re
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


NON_ORIGIN_WORDS = {
    "here", "home", "there", "the", "a", "an", "my", "your", "our", "their", "its",
    "budget", "friendly", "luxury", "cheap", "low", "cost", "moderate", "standard",
    "day", "days", "night", "nights", "week", "weeks", "month", "months",
    "yes", "no", "sure", "ok", "okay", "please", "thanks", "thank", "you",
    "trip", "trips", "travel", "travelling", "traveling", "vacation", "holiday",
    "say", "ill", "i'll", "will", "would", "like", "can", "update", "change",
    "make", "extend", "reduce", "friend", "friends", "family", "solo",
    "nightlife", "beaches", "attraction", "food", "sightseeing", "shopping", "exploration"
}


def parse_modification_intent(text: str) -> dict[str, Any]:
    """
    Parses explicit modification intents from a user query when an itinerary already exists.
    Returns dict containing updated parameters (if any): duration_days, budget, origin, preferences, intent_found.
    """
    if not text:
        return {"intent_found": False, "changes": {}}

    text_lower = text.lower().strip()
    result: dict[str, Any] = {"intent_found": False, "changes": {}}
    changes = result["changes"]

    # 1. Explicit Duration change
    # e.g., 'can you update it to 7 days trip?', 'make it 7 days', 'change to one week', 'extend by 2 days'
    m_dur = re.search(r'\b(?:make\s+it|change\s+(?:it\s+)?to|update\s+(?:it\s+)?to|extend\s+(?:by|to)|set\s+to|for)?\s*(\d+)\s*(?:day|night)s?\b', text_lower)
    if m_dur:
        try:
            val = int(m_dur.group(1))
            if 1 <= val <= 30:
                changes["duration_days"] = val
                result["intent_found"] = True
        except ValueError:
            pass

    if "duration_days" not in changes:
        m_wk = re.search(r'\b(?:make\s+it|change\s+(?:it\s+)?to|update\s+(?:it\s+)?to|set\s+to|for)?\s*(\d+)\s*weeks?\b', text_lower)
        if m_wk:
            try:
                changes["duration_days"] = int(m_wk.group(1)) * 7
                result["intent_found"] = True
            except ValueError:
                pass

    if "duration_days" not in changes:
        if re.search(r'\b(?:one week|a week|1 week)\b', text_lower):
            changes["duration_days"] = 7
            result["intent_found"] = True
        elif re.search(r'\b(?:two weeks|2 weeks)\b', text_lower):
            changes["duration_days"] = 14
            result["intent_found"] = True

    # 2. Explicit Budget change
    # e.g., 'make it luxury', 'change budget to luxury', 'reduce budget to ₹50,000', 'i'lll say budget friendly'
    if re.search(r'\b(?:luxury|5[- ]?star|five[- ]?star|no limit|unlimited)\b', text_lower):
        changes["budget"] = "Luxury"
        result["intent_found"] = True
    elif re.search(r'\b(?:budget[- ]friendly|cheap|low[- ]cost|backpack|hostel)\b', text_lower) or re.search(r'\bbudget\b', text_lower):
        changes["budget"] = "Budget-friendly"
        result["intent_found"] = True
    elif re.search(r'\b(?:mid[- ]?range|moderate|standard)\b', text_lower):
        changes["budget"] = "Mid-range"
        result["intent_found"] = True
    else:
        m_b = re.search(r'(?:[\$\u20B9\u20AC\u00A3]\s*\d[\d,]*|\d[\d,]*\s*(?:usd|inr|rs|rupees?|euros?|pounds?|gbp))', text_lower)
        if m_b:
            changes["budget"] = m_b.group(0).strip()
            result["intent_found"] = True

    # 3. Explicit Origin change
    # e.g., 'I am travelling from Ahmedabad', 'from Surat', 'my departure city is Mumbai'
    m_orig = re.search(
        r'\b(?:i am |i\'m )?(?:travellin?g|travel|departing|flying|leaving|coming)\s+from\s+([a-zA-Z][a-zA-Z\s]{1,30}?)(?:\s+to\b|\s+for\b|,|\.|$)',
        text,
        re.IGNORECASE,
    )
    if m_orig:
        cand = m_orig.group(1).strip()
        cand = re.sub(r'\s+(?:instead\s+of|rather\s+than|not)\s+.*$', '', cand, flags=re.I).strip().title()
        if cand and cand.lower() not in NON_ORIGIN_WORDS and not any(w in NON_ORIGIN_WORDS for w in cand.lower().split()):
            changes["origin"] = cand
            result["intent_found"] = True

    # 4. Preferences / Interests / Focus / Local exploration / Activities
    # e.g., 'and i want to explore local areas more', 'add nightlife', 'focus on beaches', 'more food options'
    pref_matches = []
    if re.search(r'\b(?:explore\s+local|local\s+area|local\s+exploration|offbeat|hidden\s+gems|neighborhood|neighbourhood|local\s+culture|local\s+spots)\b', text_lower):
        pref_matches.append("Local Exploration & Hidden Gems")
    if re.search(r'\b(?:nightlife|clubs?|bars?|party|parties|pub)\b', text_lower):
        pref_matches.append("Nightlife & Evening Entertainment")
    if re.search(r'\b(?:beach|beaches|coastal|water\s+sports)\b', text_lower):
        pref_matches.append("Beaches & Water Activities")
    if re.search(r'\b(?:food|cuisine|restaurants?|street\s+food|dining|dishes)\b', text_lower):
        pref_matches.append("Food & Local Cuisine")
    if re.search(r'\b(?:shopping|markets?|bazaars?)\b', text_lower):
        pref_matches.append("Shopping & Local Markets")
    if re.search(r'\b(?:relax|relaxation|spa|peaceful|quiet)\b', text_lower):
        pref_matches.append("Relaxation & Wellness")
    if re.search(r'\b(?:culture|heritage|temples?|museums?|history)\b', text_lower):
        pref_matches.append("Culture & Heritage")

    if pref_matches:
        changes["preferences"] = pref_matches
        result["intent_found"] = True

    # 5. Generic Modification Triggers Check
    # If text expresses a modification intent like 'i want to...', 'can you add...', 'modify...', 'change...', 'update...'
    if not result["intent_found"]:
        mod_triggers = [
            r'\b(?:want|would\s+like|like)\s+to\b',
            r'\b(?:can\s+you|please)?\s*(?:update|change|modify|revise|add|include|focus)\b',
            r'\bmore\b',
            r'\binstead\b',
            r'\bprefer\b',
        ]
        if any(re.search(pat, text_lower) for pat in mod_triggers):
            m_phrase = re.search(r'\b(?:want\s+to|like\s+to|add|include|focus\s+on|prefer)\s+([a-zA-Z\s]{3,40})', text_lower)
            extracted_pref = m_phrase.group(1).strip().title() if m_phrase else text.strip()
            changes["preferences"] = [extracted_pref]
            result["intent_found"] = True

    return result


def heuristic_parse(messages: list[Any], destination: str) -> dict[str, Any]:
    """Regex/keyword fallback when Gemini is unavailable."""
    user_contents: list[str] = []
    origin = None
    stop_words_dest = {
        "Here", "Home", "There", "The", "A", "An", "My", "Your", "Our", "Their",
        "Shopping", "Exploring", "Relaxing", "Relaxation", "Adventure", "Business",
        "Work", "Sightseeing", "Vacation", "Holiday", "Stay", "Travel", "Travelling",
        "Traveling", "Days", "Weeks", "Months", "Trip", "Trips", "Plan", "Tour", "Tours",
        "Flight", "Hotel", "Budget", "Luxury", "Cheap", "Exploration"
    }
    lower_stop = {s.lower() for s in stop_words_dest}

    for msg in messages:
        role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else None)
        content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)

        if not content:
            continue

        if role == "user":
            user_contents.append(content)

    text = " ".join(user_contents).lower()

    # Scan user messages from NEWEST to OLDEST for origin and duration
    for u_content in reversed(user_contents):
        u_text = u_content.strip()
        stripped = re.sub(
            r'^(?:i am |i\'m )?(?:from|traveling from|travelling from|departing from|leaving from|coming from|my departure city is|my origin is)\s+',
            '', u_text.lower(), flags=re.IGNORECASE
        ).strip()
        stripped = re.sub(r'\s+(?:instead\s+of|rather\s+than|not)\s+.*$', '', stripped, flags=re.I).strip().title()
        words = [w.lower() for w in stripped.split()]
        if stripped and len(words) <= 3 and not any(w in NON_ORIGIN_WORDS for w in words) and re.match(r'^[a-zA-Z\s]+$', stripped):
            if not origin:
                origin = stripped
                break

    if not origin:
        for u_content in reversed(user_contents):
            m = re.search(
                r'\b(?:travellin?g|travel|departing|flying|leaving|coming)\s+from\s+([a-zA-Z][a-zA-Z\s]{1,30}?)(?:\s+to\b|\s+for\b|,|\.|$)',
                u_content,
                re.IGNORECASE,
            )
            if m:
                cand = m.group(1).strip()
                cand = re.sub(r'\s+(?:instead\s+of|rather\s+than|not)\s+.*$', '', cand, flags=re.I).strip().title()
                if cand.lower() not in NON_ORIGIN_WORDS and not any(w in NON_ORIGIN_WORDS for w in cand.lower().split()):
                    origin = cand
                    break
            m = re.search(r"\bi(?:'?m| am)\s+from\s+([a-zA-Z][a-zA-Z\s]{1,20}?)(?:\s+to\b|\s+for\b|,|\.|$)", u_content, re.IGNORECASE)
            if m:
                cand = m.group(1).strip()
                cand = re.sub(r'\s+(?:instead\s+of|rather\s+than|not)\s+.*$', '', cand, flags=re.I).strip().title()
                if cand.lower() not in NON_ORIGIN_WORDS and not any(w in NON_ORIGIN_WORDS for w in cand.lower().split()):
                    origin = cand
                    break

    if not origin:
        for u_content in reversed(user_contents):
            m = re.search(r'\bfrom\s+([A-Za-z][a-z]+(?:\s+[A-Z][a-z]+)?)\b', u_content)
            if m:
                cand = m.group(1).strip()
                cand = re.sub(r'\s+(?:instead\s+of|rather\s+than|not)\s+.*$', '', cand, flags=re.I).strip().title()
                if cand.lower() not in NON_ORIGIN_WORDS and not any(w in NON_ORIGIN_WORDS for w in cand.lower().split()) and len(cand) > 2:
                    origin = cand
                    break

    # Destination override — scan from newest to oldest
    for u_content in reversed(user_contents):
        dest_match = re.search(
            r'\b(?:from\s+[a-zA-Z\s]{2,30}?\s+to|travel\s+to|travelling\s+to|traveling\s+to|trip\s+to|trip\s+for|plan\s+to|plan\s+for|details\s+of|details\s+for|visiting|go\s+to|going\s+to|to|for)\s+([a-zA-Z][a-zA-Z\s]{1,25}?)(?:\s+for\b|\s+with\b|\s+in\b|\s+on\b|,|\.|$)',
            u_content,
            re.IGNORECASE,
        )
        if dest_match:
            candidate_dest = dest_match.group(1).strip().title()
            if (
                candidate_dest not in stop_words_dest
                and candidate_dest.lower() not in lower_stop
                and len(candidate_dest) > 2
                and re.match(r'^[a-zA-Z\s]+$', candidate_dest)
            ):
                destination = candidate_dest
                break

    # Budget
    budget = None
    for u_content in reversed(user_contents):
        u_lower = u_content.lower()
        m = re.search(r'(?:[\$\u20B9\u20AC\u00A3]\s*\d[\d,]*|\d[\d,]*\s*(?:usd|inr|rs|rupees?|euros?|pounds?|gbp))', u_lower)
        if m:
            budget = m.group(0).strip()
            break
        elif re.search(r'\b(?:no limit|unlimited)\b', u_lower):
            budget = "Luxury / No limit"
            break
        elif re.search(r'\b(?:luxury|5[- ]?star|five[- ]?star)\b', u_lower):
            budget = "Luxury"
            break
        elif re.search(r'\b(?:budget[- ]friendly|cheap|low[- ]cost|backpack|hostel)\b', u_lower) or re.search(r'\bbudget\b', u_lower):
            budget = "Budget-friendly"
            break
        elif re.search(r'\b(?:mid[- ]?range|moderate|standard)\b', u_lower):
            budget = "Mid-range"
            break

    # Duration — scan user messages from NEWEST to OLDEST
    duration_days = None
    for u_content in reversed(user_contents):
        u_lower = u_content.lower()
        m = re.search(r'(\d+)\s*(?:to|-|–)\s*(\d+)\s*(?:day|night)s?', u_lower)
        if m:
            try:
                duration_days = (int(m.group(1)) + int(m.group(2))) // 2
                break
            except ValueError:
                pass
        m = re.search(r'(\d+)\s*weeks?', u_lower)
        if m:
            try:
                duration_days = int(m.group(1)) * 7
                break
            except ValueError:
                pass
        m = re.search(r'\b(\d+)\s*(?:day|night)s?\b', u_lower)
        if m:
            try:
                duration_days = int(m.group(1))
                break
            except ValueError:
                pass
        if re.search(r'\b(?:one week|a week)\b', u_lower):
            duration_days = 7
            break
        elif "weekend" in u_lower:
            duration_days = 2
            break
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
    m_goal = re.search(r'\b(?:my\s+)?(?:goal|purpose|aim|interest|want\s+to\s+do)\s*(?:is|are|:)?\s+([a-zA-Z0-9\s,&\+]{3,40}?)(?:\.|$|\n)', text, re.IGNORECASE)
    if m_goal:
        candidate_goal = m_goal.group(1).strip()
        if (
            candidate_goal.lower() not in ("a", "the", "my", "this", "trip", "travel")
            and candidate_goal.lower() not in lower_stop
            and not re.search(r'^\d+\s*(?:day|night|week)s?', candidate_goal.lower())
        ):
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
            ("exploring", "Exploration"),
            ("travelling", "Exploration"),
            ("traveling", "Exploration"),
            ("travel", "Exploration"),
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
    Uses shared call_gemini_async (rate-limited, model fallback) when configured;
    falls back to heuristics.
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

    # Always run heuristics first as a baseline — instant, zero API calls
    heuristic = heuristic_parse(messages, destination)

    # If ALL 4 core params found by heuristics, skip Gemini (save rate limit)
    heuristic_score = sum([
        bool(heuristic.get("origin")),
        bool(heuristic.get("budget")),
        bool(heuristic.get("duration_days")),
        bool(heuristic.get("goal")),
    ])
    if heuristic_score == 4:
        logger.debug("parse_travel_state: all 4 params found by heuristics — skipping Gemini")
        return heuristic

    if not settings.gemini_api_key:
        return heuristic

    try:
        from app.agents.gemini_client import call_gemini_async
        from langchain_core.messages import HumanMessage

        prompt = (
            f"You are the travel coordinator agent for VoyagerAI.\n"
            f"Analyze the chat history for a trip to '{destination}' and extract planning parameters.\n\n"
            f"CRITICAL: Do NOT guess or hallucinate. If a value is not explicitly stated, set it to null.\n"
            f"CRITICAL: NEVER output generic words like 'Travelling', 'Traveling', 'Trip', 'Vacation', 'Holiday', 'Exploration', 'Sightseeing', 'Stay', or 'Tour' as the destination city!\n\n"
            f"Return ONLY a raw JSON object (no markdown, no code blocks) with these fields:\n"
            f"- origin: string or null (city/country the user departs from)\n"
            f"- destination: string (default: '{destination}', BUT if the user explicitly asks for a different destination city in the chat history, return that city instead!)\n"
            f"- budget: string or null (e.g. '$1000', '50000 INR', 'luxury', 'no limit')\n"
            f"- duration_days: integer or null (number of trip days)\n"
            f"- dates: string or null (travel month, season, or date range)\n"
            f"- goal: string or null (primary trip purpose: honeymoon, relaxation, business, etc.)\n"
            f"- conditions: string or null (dietary, accessibility, or companion requirements)\n"
            f"- preferences: array of strings (secondary interests)\n\n"
            f"Chat History:\n{chat_history_text}"
        )

        raw = await call_gemini_async([HumanMessage(content=prompt)], timeout=6)

        # Strip markdown fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(line for line in lines if not line.startswith("```")).strip()

        parsed = json.loads(cleaned)
        extracted_dest = parsed.get("destination") or heuristic.get("destination") or destination
        lower_stop = {
            "travelling", "traveling", "travel", "trip", "trips", "tour", "tours",
            "holiday", "vacation", "stay", "relaxing", "exploring", "sightseeing",
            "business", "work", "exploration"
        }
        if isinstance(extracted_dest, str) and extracted_dest.strip().lower() in lower_stop:
            extracted_dest = destination

        extracted_origin = parsed.get("origin") or heuristic.get("origin")
        if isinstance(extracted_origin, str):
            words = [w.lower() for w in extracted_origin.split()]
            if any(w in NON_ORIGIN_WORDS for w in words):
                extracted_origin = heuristic.get("origin")
                if isinstance(extracted_origin, str):
                    words_h = [w.lower() for w in extracted_origin.split()]
                    if any(w in NON_ORIGIN_WORDS for w in words_h):
                        extracted_origin = None

        return {
            "origin": extracted_origin,
            "destination": extracted_dest,
            "budget": parsed.get("budget") or heuristic.get("budget"),
            "duration_days": parsed.get("duration_days") or heuristic.get("duration_days"),
            "dates": parsed.get("dates") or heuristic.get("dates"),
            "goal": parsed.get("goal") or heuristic.get("goal"),
            "conditions": parsed.get("conditions") or heuristic.get("conditions"),
            "preferences": parsed.get("preferences") or heuristic.get("preferences") or [],
        }
    except Exception:
        logger.exception("Gemini parse_travel_state failed — using heuristics")

    return heuristic
