import jwt
from cryptography.hazmat.primitives.asymmetric import ec

from app.agents.coordinator import coordinator_graph
from app.core import security
from app.core.config import get_settings


def test_protected_routes_require_a_bearer_token(client):
    response = client.get("/api/v1/trips")
    assert response.status_code == 401


def test_cors_preflight_is_not_blocked_by_jwt_middleware(client):
    response = client.options(
        "/api/v1/trips",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_es256_token_uses_jwks_even_when_a_legacy_secret_is_configured(monkeypatch):
    private_key = ec.generate_private_key(ec.SECP256R1())
    token = jwt.encode(
        {"sub": "d1a92d18-80f4-4e46-ae16-a2e7928e47cc", "email": "es@example.com", "aud": "authenticated"},
        private_key,
        algorithm="ES256",
        headers={"kid": "supabase-key"},
    )

    class SigningKey:
        key = private_key.public_key()

    class FakeJwksClient:
        def get_signing_key_from_jwt(self, received_token):
            assert received_token == token
            return SigningKey()

    settings = get_settings()
    old_url, old_secret = settings.supabase_url, settings.supabase_jwt_secret
    settings.supabase_url = "https://example.supabase.co"
    settings.supabase_jwt_secret = "legacy-secret-must-not-be-used-for-es256"
    monkeypatch.setattr(security, "get_jwks_client", lambda _: FakeJwksClient())
    try:
        assert security.verify_access_token(token).email == "es@example.com"
    finally:
        settings.supabase_url, settings.supabase_jwt_secret = old_url, old_secret


def test_trip_chat_is_persisted_and_reloaded(client, auth_headers):
    trip_response = client.post("/api/v1/trips", headers=auth_headers, json={"destination": "Tokyo"})
    assert trip_response.status_code == 201
    trip = trip_response.json()

    chat_response = client.post(
        f"/api/v1/trips/{trip['id']}/messages",
        headers=auth_headers,
        json={"content": "I enjoy food and museums", "budget": "₹100000", "preferences": ["food", "culture"]},
    )
    assert chat_response.status_code == 200
    coord_msg_content = chat_response.json()["coordinator_message"]["content"]
    assert "Planning has started for Tokyo" in coord_msg_content or "completed VoyagerAI" in coord_msg_content

    messages = client.get(f"/api/v1/trips/{trip['id']}/messages", headers=auth_headers)
    assert messages.status_code == 200
    assert [message["role"] for message in messages.json()] == ["user", "assistant"]


def test_coordinator_graph_returns_structured_planning_response():
    result = coordinator_graph.invoke({
        "destination": "Lisbon", "dates": "June", "budget": "€900", "preferences": ["food"],
        "user_message": "Plan a short trip", "agent_outputs": {},
    })
    output = result["agent_outputs"]["coordinator"]
    assert output["status"] == "planning_started"
    assert output["trip_context"]["destination"] == "Lisbon"
