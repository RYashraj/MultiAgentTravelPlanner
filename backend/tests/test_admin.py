"""
Tests for Admin Endpoints and Server-Side Authorization Enforcement.
"""
from app.db.models import AgentRun, Trip
import uuid


def test_admin_stats_forbidden_for_regular_user(client):
    # Regular non-admin user token
    headers = {"Authorization": "Bearer mock-regularuser@example.com"}
    res = client.get("/api/v1/admin/stats", headers=headers)
    assert res.status_code == 403
    data = res.json()
    assert "Forbidden" in data["detail"]


def test_admin_stats_allowed_for_admin_user(client, db_session):
    # Admin user token
    headers = {"Authorization": "Bearer mock-admin@example.com"}
    res = client.get("/api/v1/admin/stats", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert "metrics" in data
    assert "total_trips" in data["metrics"]
    assert "total_users" in data["metrics"]
    assert "total_agent_runs" in data["metrics"]
    assert "recent_agent_runs" in data


def test_admin_stats_returns_real_agent_run_data(client, db_session):
    headers = {"Authorization": "Bearer mock-admin@voyager.ai"}

    # Insert a test trip and agent run into test DB
    user_id = uuid.uuid4()
    trip = Trip(id=uuid.uuid4(), user_id=user_id, destination="Paris", status="planning")
    db_session.add(trip)
    db_session.commit()

    agent_run = AgentRun(
        trip_id=trip.id,
        agent_name="FlightAgent",
        status="completed",
        input_payload={"destination": "Paris"},
        output_payload={"flights": []},
    )
    db_session.add(agent_run)
    db_session.commit()

    res = client.get("/api/v1/admin/stats", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["metrics"]["total_agent_runs"] >= 1
    assert data["metrics"]["completed_agent_runs"] >= 1
    assert any(run["agent_name"] == "FlightAgent" for run in data["recent_agent_runs"])
