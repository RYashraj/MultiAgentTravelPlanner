"""
Tests for Global Exception Handling and Input Validation Audit.
Verifies error masking in production, Pydantic validation boundaries,
and clean error responses for invalid inputs.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import get_settings


def test_invalid_destination_whitespace(client, auth_headers):
    # Whitespace-only destination should be rejected with 422
    res = client.post("/api/v1/trips", json={"destination": "   "}, headers=auth_headers)
    assert res.status_code == 422
    data = res.json()
    assert data["detail"] == "Input validation failed"
    assert any("destination" in err.get("field", "").lower() for err in data.get("errors", []))


def test_invalid_destination_length(client, auth_headers):
    # Too short (1 char)
    res_short = client.post("/api/v1/trips", json={"destination": "A"}, headers=auth_headers)
    assert res_short.status_code == 422

    # Too long (> 255 chars)
    res_long = client.post("/api/v1/trips", json={"destination": "A" * 256}, headers=auth_headers)
    assert res_long.status_code == 422


def test_invalid_trip_uuid(client, auth_headers):
    # Malformed UUID string in path parameter
    res = client.get("/api/v1/trips/not-a-valid-uuid", headers=auth_headers)
    assert res.status_code == 422
    data = res.json()
    assert data["detail"] == "Input validation failed"


def test_invalid_message_content(client, auth_headers):
    # 1. Create valid trip
    trip_res = client.post("/api/v1/trips", json={"destination": "Tokyo"}, headers=auth_headers)
    trip_id = trip_res.json()["id"]

    # 2. Empty / whitespace message content
    res_empty = client.post(
        f"/api/v1/trips/{trip_id}/messages",
        json={"content": "    "},
        headers=auth_headers
    )
    assert res_empty.status_code == 422

    # 3. Content exceeding 4000 chars
    res_too_long = client.post(
        f"/api/v1/trips/{trip_id}/messages",
        json={"content": "X" * 4001},
        headers=auth_headers
    )
    assert res_too_long.status_code == 422


def test_invalid_query_param(client, auth_headers):
    # Invalid boolean for saved filter
    res = client.get("/api/v1/trips?saved=not_a_boolean", headers=auth_headers)
    assert res.status_code == 422


def test_production_error_masking(monkeypatch):
    # Test that unhandled 500 exceptions in production mode mask stack traces and internal secrets
    settings = get_settings()
    monkeypatch.setattr(settings, "environment", "production")

    @app.get("/api/v1/test-unhandled-error")
    def dummy_error_route():
        raise RuntimeError("Sensitive internal database connection string: postgres://user:secret@db.internal:5432/mydb")

    test_client = TestClient(app, raise_server_exceptions=False)
    res = test_client.get("/api/v1/test-unhandled-error")
    assert res.status_code == 500
    data = res.json()
    assert "postgres" not in data["detail"].lower()
    assert "secret" not in data["detail"].lower()
    assert data["detail"] == "An internal server error occurred. Please try again later."
