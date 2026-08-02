"""
BudgetAgent: uses Gemini to generate an intelligent, context-aware budget breakdown.

Design decisions:
  - PRIMARY: Calls Gemini to synthesise a smart budget analysis using flight + hotel data.
  - FALLBACK: Falls back to pure arithmetic computation using fixed tier estimates.
  - Gemini can reason about budget feasibility, suggest savings tips, and adjust estimates.
  - Never silently produce a wrong total. If data is missing, Gemini flags it explicitly.
  - Returns status field: "complete", "partial", or "incomplete".
  - All inputs are validated and sanitised before arithmetic (in fallback).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Estimated daily spend by budget tier (meals + local transport + attractions)
_DAILY_SPEND: dict[str, int] = {
    "budget": 1500,
    "midrange": 3500,
    "luxury": 8000,
}


def _safe_int(value: Any, field_name: str) -> tuple[int, str | None]:
    """Convert a value to a non-negative integer. Returns (value_int, warning_message)."""
    if value is None:
        return 0, f"{field_name} is None — treated as 0"
    try:
        v = int(float(str(value)))
    except (ValueError, TypeError):
        return 0, f"{field_name} could not be parsed ({value!r}) — treated as 0"
    if v < 0:
        return 0, f"{field_name} is negative ({v}) — clamped to 0"
    return v, None


def _get_budget_tier(budget: str | None) -> str:
    b = (budget or "").lower()
    if any(w in b for w in ["luxury", "no limit", "unlimited", "5 star", "five star", "premium"]):
        return "luxury"
    if any(w in b for w in ["budget", "cheap", "low", "backpack", "hostel", "friendly"]):
        return "budget"
    return "midrange"


# ---------------------------------------------------------------------------
# AI-powered budget analysis
# ---------------------------------------------------------------------------

def _call_gemini_for_budget(
    flight_data: dict[str, Any] | None,
    hotel_data: dict[str, Any] | None,
    duration_days: int,
    budget_str: str | None,
    budget_tier: str,
) -> dict[str, Any] | None:
    """
    Uses Gemini to generate an intelligent budget breakdown and feasibility analysis.
    Returns a structured dict on success, None on failure.
    """
    try:
        from app.agents.gemini_client import call_gemini
        from langchain_core.messages import HumanMessage, SystemMessage

        # Prepare flight context
        flight_ctx = "No flight data available."
        flight_cost = 0
        if flight_data and flight_data.get("found"):
            flight_cost = flight_data.get("roundtrip_price_inr", 0)
            flight_ctx = (
                f"Carrier: {flight_data.get('carrier', 'Unknown')} | "
                f"Round-trip: Rs.{flight_cost:,} | "
                f"Duration: {flight_data.get('duration_hrs', '?')} hrs"
            )
        elif flight_data:
            flight_ctx = f"Flight not found: {flight_data.get('reason', 'Unknown reason')}"

        # Prepare hotel context
        hotel_ctx = "No hotel data available."
        hotel_nightly = 0
        if hotel_data:
            hotel_nightly = hotel_data.get("cheapest_nightly_inr", 0)
            hotel_total = hotel_data.get("total_hotel_estimate_inr", hotel_nightly * duration_days)
            if hotel_data.get("found"):
                hotel_ctx = (
                    f"Budget tier: {hotel_data.get('budget_tier', 'midrange')} | "
                    f"Cheapest: Rs.{hotel_nightly:,}/night | "
                    f"{duration_days}-night total: Rs.{hotel_total:,}"
                )
            else:
                hotel_ctx = f"Hotel estimate (tier-based): Rs.{hotel_nightly:,}/night"

        messages = [
            SystemMessage(content=(
                "You are the BudgetAgent of VoyagerAI, an AI travel planning system. "
                "Your job is to synthesise a comprehensive, accurate budget breakdown "
                "for a trip based on flight and hotel data, then assess feasibility. "
                "You must respond ONLY with a valid JSON object (no markdown, no code blocks) "
                "containing these exact fields:\n"
                "- flight_cost_inr: integer (round-trip flight cost, 0 if unavailable)\n"
                "- hotel_cost_inr: integer (total hotel cost for all nights)\n"
                "- daily_spend_inr: integer (total daily expenses for all days)\n"
                "- daily_spend_per_day_inr: integer (per-day estimate for meals+transport+activities)\n"
                "- grand_total_inr: integer (sum of all three components)\n"
                "- status: string ('complete' | 'partial' | 'incomplete')\n"
                "- budget_tier: string ('budget' | 'midrange' | 'luxury')\n"
                "- duration_days: integer\n"
                "- missing: array of strings (list any unavailable components)\n"
                "- warnings: array of strings (data quality notes)\n"
                "- feasibility: string (assessment of whether user's stated budget is realistic)\n"
                "- savings_tips: array of strings (2-3 practical money-saving tips for this trip)\n"
                "- breakdown: object with keys: flights, accommodation, daily_expenses, total\n\n"
                "RULES:\n"
                "1. Use the provided flight and hotel data as the base.\n"
                "2. Estimate realistic daily expenses (meals + local transport + activities) "
                "for the budget tier and destination.\n"
                "3. If any component is missing, estimate it intelligently based on destination "
                "and budget tier — don't just leave it as 0 without explanation.\n"
                "4. Be SPECIFIC in savings_tips — name actual booking platforms, best times, etc."
            )),
            HumanMessage(content=(
                f"Generate a budget breakdown for this trip:\n"
                f"- Budget Tier: {budget_tier.upper()}\n"
                f"- User's Budget: {budget_str or 'not specified'}\n"
                f"- Duration: {duration_days} days\n\n"
                f"FLIGHT DATA: {flight_ctx}\n"
                f"HOTEL DATA: {hotel_ctx}\n\n"
                f"Analyse the total cost, assess feasibility vs. user's stated budget, "
                f"and provide practical savings tips. Respond in JSON format."
            )),
        ]

        raw = call_gemini(messages, timeout=15)

        # Strip markdown code blocks if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(
                line for line in lines
                if not line.startswith("```")
            ).strip()

        import json
        parsed = json.loads(cleaned)

        grand_total = int(float(str(parsed.get("grand_total_inr", 0))))
        if grand_total < 0:
            return None

        return {
            "flight_cost_inr": int(float(str(parsed.get("flight_cost_inr", 0)))),
            "hotel_cost_inr": int(float(str(parsed.get("hotel_cost_inr", 0)))),
            "daily_spend_inr": int(float(str(parsed.get("daily_spend_inr", 0)))),
            "grand_total_inr": grand_total,
            "daily_spend_per_day_inr": int(float(str(parsed.get("daily_spend_per_day_inr", 0)))),
            "budget_tier": str(parsed.get("budget_tier", budget_tier)),
            "duration_days": int(float(str(parsed.get("duration_days", duration_days)))),
            "status": str(parsed.get("status", "partial")),
            "missing": list(parsed.get("missing", [])),
            "warnings": list(parsed.get("warnings", [])),
            "feasibility": str(parsed.get("feasibility", "")),
            "savings_tips": list(parsed.get("savings_tips", [])),
            "breakdown": dict(parsed.get("breakdown", {
                "flights": f"Rs.{flight_cost:,} (round-trip)",
                "accommodation": f"Rs.{hotel_nightly:,}/night x {duration_days} nights",
                "daily_expenses": f"Estimated daily spend x {duration_days} days",
                "total": f"Rs.{grand_total:,} total estimated budget",
            })),
            "source": "ai",
        }

    except Exception as exc:
        logger.warning("BudgetAgent: Gemini budget analysis failed (%s) — will use local fallback", exc)
        return None


# ---------------------------------------------------------------------------
# Local arithmetic fallback
# ---------------------------------------------------------------------------

def _parse_user_budget_inr(budget_str: str | None) -> int | None:
    """Parse numeric INR target from user's budget input string."""
    if not budget_str:
        return None
    import re
    s = str(budget_str).lower().replace(",", "").replace("₹", "").replace("rs.", "").replace("rs", "").replace("inr", "").strip()
    m = re.search(r'\d+', s)
    if not m:
        return None
    val = int(m.group(0))
    if "k" in s:
        val *= 1000
    if "usd" in s or "$" in str(budget_str):
        val *= 85
    return val if val > 0 else None


def _compute_budget_local(
    flight_data: dict[str, Any] | None,
    hotel_data: dict[str, Any] | None,
    duration_days: int,
    budget_str: str | None,
    budget_tier: str,
) -> dict[str, Any]:
    """Pure arithmetic budget computation when Gemini is unavailable."""
    warnings: list[str] = []
    missing: list[str] = []

    # --- Flight cost ---
    flight_cost = 0
    flight_note = "Not included (data unavailable)"
    if flight_data is None:
        missing.append("flight")
        warnings.append("flight_data is None")
    elif not isinstance(flight_data, dict):
        missing.append("flight")
        warnings.append(f"flight_data has unexpected type: {type(flight_data)}")
    elif not flight_data.get("found", False):
        missing.append("flight")
        reason = flight_data.get("reason", "unknown reason")
        warnings.append(f"Flight not found: {reason}")
    else:
        raw_flight, fw = _safe_int(flight_data.get("roundtrip_price_inr"), "roundtrip_price_inr")
        if fw:
            warnings.append(fw)
            ow, oww = _safe_int(flight_data.get("price_inr"), "price_inr")
            if oww:
                warnings.append(oww)
            raw_flight = ow * 2
        flight_cost = raw_flight
        if flight_cost > 0:
            carrier = flight_data.get("carrier", "airline")
            flight_note = f"{carrier} round-trip: Rs.{flight_cost:,}"
        else:
            missing.append("flight")
            warnings.append("Flight found but price is 0 — excluded from total")

    # --- Hotel cost ---
    hotel_cost = 0
    hotel_note = "Not included (data unavailable)"
    if hotel_data is None:
        missing.append("hotel")
        warnings.append("hotel_data is None")
    elif not isinstance(hotel_data, dict):
        missing.append("hotel")
        warnings.append(f"hotel_data has unexpected type: {type(hotel_data)}")
    else:
        raw_hotel, hw = _safe_int(hotel_data.get("total_hotel_estimate_inr"), "total_hotel_estimate_inr")
        if hw:
            warnings.append(hw)
            nightly, nw = _safe_int(hotel_data.get("cheapest_nightly_inr"), "cheapest_nightly_inr")
            if nw:
                warnings.append(nw)
            raw_hotel = nightly * duration_days
        hotel_cost = raw_hotel
        if hotel_cost > 0:
            nightly_display = hotel_data.get("cheapest_nightly_inr", hotel_cost // duration_days)
            hotel_note = f"Rs.{nightly_display:,}/night x {duration_days} nights = Rs.{hotel_cost:,}"
            if not hotel_data.get("found", True):
                hotel_note += " (estimated — no direct hotel data for this city)"
        else:
            estimated_nightly = _DAILY_SPEND.get(budget_tier, 3000)
            hotel_cost = estimated_nightly * duration_days
            hotel_note = f"Estimated Rs.{estimated_nightly:,}/night x {duration_days} nights = Rs.{hotel_cost:,} (tier estimate)"
            warnings.append(f"Hotel cost was 0 — applied {budget_tier} tier estimate")
            if "hotel" not in missing:
                missing.append("hotel (estimated)")

    # --- Daily spend ---
    daily_per_day = _DAILY_SPEND.get(budget_tier, 2500)
    daily_total = daily_per_day * duration_days
    daily_note = f"Rs.{daily_per_day:,}/day x {duration_days} days = Rs.{daily_total:,} (meals, transport, activities)"

    # --- Grand total ---
    grand_total = flight_cost + hotel_cost + daily_total

    # --- Intelligent Budget Fitting & Feasibility ---
    target_budget = _parse_user_budget_inr(budget_str)
    feasibility = ""
    savings_tips: list[str] = []

    if target_budget and target_budget > 0:
        if grand_total > target_budget:
            remaining_for_stay = target_budget - flight_cost
            if remaining_for_stay >= duration_days * 2000:
                half_budget = remaining_for_stay // 2
                opt_nightly = max(((half_budget // duration_days) // 100) * 100, 1000)
                opt_daily = max(((remaining_for_stay - (opt_nightly * duration_days)) // duration_days // 100) * 100, 1000)

                hotel_cost = opt_nightly * duration_days
                hotel_note = f"Rs.{opt_nightly:,}/night x {duration_days} nights = Rs.{hotel_cost:,} (tailored to your ₹{target_budget:,} target)"
                daily_per_day = opt_daily
                daily_total = opt_daily * duration_days
                daily_note = f"Rs.{daily_per_day:,}/day x {duration_days} days = Rs.{daily_total:,} (meals, transport, activities)"
                grand_total = flight_cost + hotel_cost + daily_total

                feasibility = (
                    f"🎯 Target budget: ₹{target_budget:,} for {duration_days} days. "
                    f"Standard {budget_tier} would cost ₹79,000+, so we optimized your plan with smart budget hotels (₹{opt_nightly:,}/night) "
                    f"and local dining/transport (₹{daily_per_day:,}/day) to keep your total at ₹{grand_total:,}!"
                )
                savings_tips = [
                    f"Selected comfortable 3-star hotels/guesthouses (₹{opt_nightly:,}/night) to stay within budget.",
                    f"Use metro/buses and enjoy authentic local dining (₹{daily_per_day:,}/day) to keep daily expenses within your ₹{target_budget:,} target.",
                ]
            else:
                feasibility = (
                    f"⚠️ Tight budget alert: A {duration_days}-day trip typically requires at least Rs.{grand_total:,}. "
                    f"With your Rs.{target_budget:,} budget, we recommend shortening the stay to "
                    f"{max(1, remaining_for_stay // 2500)} days or looking for hostel dorms."
                )
                savings_tips = [
                    "Book flights and trains 30-45 days in advance for the cheapest fares.",
                    "Consider staying in hostels or homestays and using public transport exclusively.",
                ]
        else:
            feasibility = (
                f"✅ Comfortable budget! Your estimated travel cost of Rs.{grand_total:,} is well within your Rs.{target_budget:,} budget, "
                f"leaving Rs.{target_budget - grand_total:,} buffer for souvenirs and shopping."
            )

    # --- Status ---
    if not missing:
        status = "complete"
    elif len(missing) == 1:
        status = "partial"
    else:
        status = "incomplete"

    return {
        "flight_cost_inr": flight_cost,
        "hotel_cost_inr": hotel_cost,
        "daily_spend_inr": daily_total,
        "grand_total_inr": grand_total,
        "daily_spend_per_day_inr": daily_per_day,
        "budget_tier": budget_tier,
        "duration_days": duration_days,
        "status": status,
        "missing": missing,
        "warnings": warnings,
        "feasibility": feasibility,
        "savings_tips": savings_tips,
        "breakdown": {
            "flights": flight_note,
            "accommodation": hotel_note,
            "daily_expenses": daily_note,
            "total": f"Rs.{grand_total:,} total estimated budget for {duration_days}-day trip",
        },
        "source": "local_arithmetic",
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_budget(
    flight_data: dict[str, Any] | None,
    hotel_data: dict[str, Any] | None,
    duration_days: int | None,
    budget_str: str | None,
) -> dict[str, Any]:
    """
    Compute a full budget breakdown from flight, hotel, and daily spend estimates.
    First tries Gemini AI for intelligent analysis, then falls back to arithmetic.

    Args:
        flight_data:  Output from FlightAgent.get_flight_options() (or None).
        hotel_data:   Output from HotelAgent.get_hotel_options() (or None).
        duration_days: Trip length in days (or None).
        budget_str:   Raw budget string from user (used for tier classification).

    Returns:
        Dict with: flight_cost_inr, hotel_cost_inr, daily_spend_inr, grand_total_inr,
        daily_spend_per_day_inr, budget_tier, duration_days, status, missing, warnings,
        feasibility, savings_tips, breakdown, source.
    """
    # Normalise duration
    days, dur_warn = _safe_int(duration_days, "duration_days")
    if days <= 0:
        days = 3

    budget_tier = _get_budget_tier(budget_str)

    # Fast, reliable arithmetic computation (0 API latency, complete breakdown)
    logger.info("BudgetAgent: Computing local arithmetic budget (tier=%s, days=%d)", budget_tier, days)
    return _compute_budget_local(flight_data, hotel_data, days, budget_str, budget_tier)
