"""
Tests for Structured Logging, Request ID propagation, and safe Sentry integration.
"""
import pytest
from app.core.config import get_settings
from app.core.logging import setup_sentry


def test_request_id_header_generated(client):
    # GET /health should automatically generate X-Request-ID header
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert "X-Request-ID" in res.headers
    assert res.headers["X-Request-ID"].startswith("req_")


def test_request_id_header_preserved(client):
    # Custom client X-Request-ID header should be preserved and returned
    custom_id = "req_custom_test_12345"
    res = client.get("/api/v1/health", headers={"X-Request-ID": custom_id})
    assert res.status_code == 200
    assert res.headers.get("X-Request-ID") == custom_id


def test_sentry_disabled_safely_when_no_dsn(monkeypatch):
    # When SENTRY_DSN is empty, setup_sentry() must return False and not crash
    settings = get_settings()
    monkeypatch.setattr(settings, "sentry_dsn", "")
    assert setup_sentry() is False


def test_sensitive_headers_masked_in_logs(client, caplog):
    # Requests with Bearer tokens or sensitive headers must not log secret values
    headers = {
        "Authorization": "Bearer secret_fake_jwt_token_12345",
        "X-Custom-Secret": "super_secret_key"
    }
    with caplog.at_level("INFO"):
        res = client.get("/api/v1/health", headers=headers)
        assert res.status_code == 200
        # Ensure secret values are NOT leaked in log text
        for record in caplog.records:
            assert "secret_fake_jwt_token_12345" not in record.message
            assert "super_secret_key" not in record.message
