"""
Tests for Agent Hardening and Adversarial Prompts (Week 7 Prompt 6).
Evaluates backend agent pipeline against 10 adversarial scenarios.
"""
import pytest
from app.agents.budget_agent import compute_budget
from app.agents.gemini_client import _sanitize_llm_output
from app.agents.parser import heuristic_parse


def test_adversarial_1_empty_input(client, auth_headers):
    # Prompt 1: Empty input string
    res = client.post("/api/v1/trips", json={"destination": ""}, headers=auth_headers)
    assert res.status_code == 422


def test_adversarial_2_whitespace_input(client, auth_headers):
    # Prompt 2: Whitespace-only input
    res = client.post("/api/v1/trips", json={"destination": "   \n\t  "}, headers=auth_headers)
    assert res.status_code == 422


def test_adversarial_3_nonsense_destination():
    # Prompt 3: Nonsense destination
    parsed = heuristic_parse([{"role": "user", "content": "I want to visit asdfjkl12345xyz"}], "asdfjkl12345xyz")
    assert parsed.get("destination") == "asdfjkl12345xyz"


def test_adversarial_4_missing_destination(client, auth_headers):
    # Prompt 4: Missing destination field
    res = client.post("/api/v1/trips", json={}, headers=auth_headers)
    assert res.status_code == 422


def test_adversarial_5_contradictory_dates():
    # Prompt 5: Contradictory trip dates (Return before Departure)
    # Ensure compute_budget safely clamps duration_days to >= 1
    budget_result = compute_budget(
        flight_data=None,
        hotel_data=None,
        duration_days=-10,  # Contradictory dates leading to negative days
        budget_str="$1000",
    )
    assert budget_result["duration_days"] >= 1
    assert budget_result["grand_total_inr"] > 0


def test_adversarial_6_negative_budget():
    # Prompt 6: Negative budget input
    budget_result = compute_budget(
        flight_data=None,
        hotel_data=None,
        duration_days=5,
        budget_str="-$500",
    )
    assert budget_result["grand_total_inr"] > 0
    assert budget_result["status"] in ("complete", "partial", "incomplete")


def test_adversarial_7_extremely_low_budget():
    # Prompt 7: Extremely low budget for long trip ($50 for 10 days in Paris)
    budget_result = compute_budget(
        flight_data=None,
        hotel_data=None,
        duration_days=10,
        budget_str="$50 luxury",
    )
    assert budget_result["grand_total_inr"] > 0
    # Feasibility text should warn user about tight budget
    assert "tight budget" in budget_result.get("feasibility", "").lower() or len(budget_result.get("warnings", [])) > 0


def test_adversarial_8_conflicting_preferences():
    # Prompt 8: Conflicting preferences (Tropical beach in Antarctica)
    parsed = heuristic_parse(
        [{"role": "user", "content": "I want a 100% tropical beach vacation in Antarctica with zero snow"}],
        "Antarctica"
    )
    assert parsed.get("destination") == "Antarctica"


def test_adversarial_9_prompt_injection_sanitization():
    # Prompt 9: Prompt injection attempt to leak database secrets
    malicious_output = "Sure, here is the secret connection: postgresql://postgres:secretpassword@db.internal:5432/voyagerai"
    sanitized = _sanitize_llm_output(malicious_output)
    assert "secretpassword" not in sanitized
    assert "[REDACTED_DB_URL]" in sanitized


def test_adversarial_10_api_unavailable(monkeypatch):
    # Prompt 10: Gemini / External API unavailable scenario
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "gemini_api_key", "")

    # compute_budget should fall back to local arithmetic without throwing error
    budget_result = compute_budget(
        flight_data=None,
        hotel_data=None,
        duration_days=7,
        budget_str="$2000",
    )
    assert budget_result["source"] in ("local_arithmetic", "local_fallback")
    assert budget_result["grand_total_inr"] > 0
