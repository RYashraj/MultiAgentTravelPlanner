import uuid
import pytest
from app.db.models import Trip, User, Itinerary
from app.tools.packing import generate_packing_list


@pytest.fixture(autouse=True)
def cleanup_trips(db_session):
    yield
    db_session.query(Trip).delete()
    db_session.commit()


def test_toggle_save_trip(client, auth_headers):
    # 1. Create a trip
    response = client.post(
        "/api/v1/trips", 
        json={"destination": "Manali"},
        headers=auth_headers
    )
    assert response.status_code == 201
    trip_id = response.json()["id"]
    assert response.json()["is_saved"] is False

    # 2. Toggle save (save)
    save_response = client.post(
        f"/api/v1/trips/{trip_id}/save",
        headers=auth_headers
    )
    assert save_response.status_code == 200
    assert save_response.json()["is_saved"] is True

    # 3. Toggle save again (unsave)
    unsave_response = client.post(
        f"/api/v1/trips/{trip_id}/save",
        headers=auth_headers
    )
    assert unsave_response.status_code == 200
    assert unsave_response.json()["is_saved"] is False


def test_list_saved_trips_filter(client, auth_headers):
    # 1. Create two trips
    trip1 = client.post("/api/v1/trips", json={"destination": "Goa"}, headers=auth_headers).json()
    trip2 = client.post("/api/v1/trips", json={"destination": "Ladakh"}, headers=auth_headers).json()

    # 2. Save one trip (Goa)
    client.post(f"/api/v1/trips/{trip1['id']}/save", headers=auth_headers)

    # 3. List all trips
    all_res = client.get("/api/v1/trips", headers=auth_headers)
    assert all_res.status_code == 200
    all_trips = all_res.json()
    assert len(all_trips) >= 2

    # 4. List only saved trips
    saved_res = client.get("/api/v1/trips?saved=true", headers=auth_headers)
    assert saved_res.status_code == 200
    saved_trips = saved_res.json()
    assert len(saved_trips) == 1
    assert saved_trips[0]["destination"] == "Goa"
    assert saved_trips[0]["is_saved"] is True

    # 5. List only unsaved trips
    unsaved_res = client.get("/api/v1/trips?saved=false", headers=auth_headers)
    assert unsaved_res.status_code == 200
    unsaved_trips = unsaved_res.json()
    assert any(t["destination"] == "Ladakh" for t in unsaved_trips)
    assert all(t["is_saved"] is False for t in unsaved_trips)


def test_packing_list_rules():
    # Rainy + 5 days + Beach
    beach_rainy = generate_packing_list("Rainy", 5, "beach")
    assert "Swimwear (swim trunks / bikini)" in beach_rainy
    assert "Compact umbrella" in beach_rainy
    assert "Underwear (x5)" in beach_rainy

    # Cold + 3 days + Adventure
    cold_adv = generate_packing_list("Snowy and freezing", 3, "adventure")
    assert "Sturdy hiking boots / trail runners" in cold_adv
    assert "Heavy winter coat / thermal jacket" in cold_adv
    assert "Underwear (x3)" in cold_adv

    # Sunny + 2 days + City (default)
    sunny_city = generate_packing_list("Sunny & Hot", 2, "city")
    assert "Polarized sunglasses" in sunny_city
    assert "Smart casual outfits for dining out" in sunny_city
    assert "Underwear (x2)" in sunny_city


@pytest.mark.anyio
async def test_dashboard_contains_packing_list(client, auth_headers, db_session):
    # 1. Create a trip
    trip_res = client.post("/api/v1/trips", json={"destination": "Goa"}, headers=auth_headers)
    trip_id = trip_res.json()["id"]

    # 2. Add an itinerary to bypass "no itinerary" dashboard error if any, or just get dashboard
    # Since dashboard returns weather, budget, flights, attractions, and packing list even without itinerary, let's fetch it.
    db = db_session
    # Set up basic itinerary in DB to mimic fully planning status
    itinerary = Itinerary(trip_id=uuid.UUID(trip_id), content="Day 1: Beach Day", status="ready")
    db.add(itinerary)
    db.commit()

    # 3. Retrieve dashboard
    res = client.get(f"/api/v1/trips/{trip_id}/dashboard", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    
    # 4. Verify packing list exists
    assert "packing_list" in data
    packing = data["packing_list"]
    assert packing["status"] == "ok"
    assert "items" in packing["data"]
    assert len(packing["data"]["items"]) > 0
    # Goa is beach destination by keywords
    assert packing["data"]["destination_type"] == "beach"
    assert "is_saved" in data
    assert data["is_saved"] is False
