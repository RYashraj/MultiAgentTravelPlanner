"""
Tests for Rate Limiting Middleware and Concurrency Proof.
Verifies HTTP 429 Too Many Requests responses, headers, and burst rate limiting.
"""
import concurrent.futures
import pytest
from app.core.config import get_settings
from app.core.rate_limiter import get_rate_limiter


@pytest.fixture(autouse=True)
def reset_limiter_state():
    """Reset rate limiter state before each test."""
    limiter = get_rate_limiter()
    limiter._records.clear()
    yield
    limiter._records.clear()


def test_auth_route_rate_limiting(client, auth_headers, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limiting_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_auth_rpm", 5)

    # Send 5 valid requests (under limit)
    for _ in range(5):
        res = client.get("/api/v1/auth/me", headers=auth_headers)
        assert res.status_code == 200
        assert "X-RateLimit-Remaining" in res.headers

    # 6th request must trigger HTTP 429 Too Many Requests
    blocked_res = client.get("/api/v1/auth/me", headers=auth_headers)
    assert blocked_res.status_code == 429
    data = blocked_res.json()
    assert data["detail"] == "Rate limit exceeded. Please wait before retrying."
    assert "retry_after_seconds" in data
    assert "Retry-After" in blocked_res.headers
    assert blocked_res.headers["X-RateLimit-Remaining"] == "0"


def test_general_route_rate_limiting(client, auth_headers, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limiting_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_general_rpm", 3)

    # Send 3 requests
    for _ in range(3):
        res = client.get("/api/v1/trips", headers=auth_headers)
        assert res.status_code == 200

    # 4th request must trigger 429
    blocked = client.get("/api/v1/trips", headers=auth_headers)
    assert blocked.status_code == 429


def test_concurrent_request_burst(client, auth_headers, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limiting_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_general_rpm", 5)

    def _make_req():
        return client.get("/api/v1/trips", headers=auth_headers).status_code

    # Fire 10 concurrent HTTP requests simultaneously across threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(_make_req) for _ in range(10)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    success_count = results.count(200)
    limited_count = results.count(429)

    assert success_count == 5
    assert limited_count == 5
