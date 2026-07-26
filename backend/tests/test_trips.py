def test_create_trip(client, auth_headers):
    # Test unauthorized request
    response = client.post("/api/v1/trips", json={"destination": "Tokyo"})
    assert response.status_code == 401

    # Test authorized request
    response = client.post(
        "/api/v1/trips", 
        json={"destination": "Tokyo"},
        headers=auth_headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["destination"] == "Tokyo"
    assert body["status"] == "draft"
    assert "id" in body


def test_list_trips(client, auth_headers):
    # Insert multiple trips for the user
    client.post("/api/v1/trips", json={"destination": "Paris"}, headers=auth_headers)
    client.post("/api/v1/trips", json={"destination": "Rome"}, headers=auth_headers)

    response = client.get("/api/v1/trips", headers=auth_headers)
    assert response.status_code == 200
    trips = response.json()
    assert len(trips) >= 2
    # Ensure they belong to the user
    for trip in trips:
        assert trip["destination"] in ["Tokyo", "Paris", "Rome"]


def test_send_and_get_messages(client, auth_headers):
    # 1. Create a trip
    trip_res = client.post("/api/v1/trips", json={"destination": "London"}, headers=auth_headers)
    trip_id = trip_res.json()["id"]

    # 2. Post a message (non-stream)
    msg_res = client.post(
        f"/api/v1/trips/{trip_id}/messages?stream=false", 
        json={"content": "Please suggest a 3 day relaxation plan for June with a 2000 usd budget"},
        headers=auth_headers
    )
    assert msg_res.status_code == 200
    body = msg_res.json()
    assert "user_message" in body
    assert "coordinator_message" in body
    assert body["user_message"]["content"] == "Please suggest a 3 day relaxation plan for June with a 2000 usd budget"
    assert "Test Itinerary" in body["coordinator_message"]["content"]

    # 3. Retrieve messages
    list_res = client.get(f"/api/v1/trips/{trip_id}/messages", headers=auth_headers)
    assert list_res.status_code == 200
    messages = list_res.json()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


def test_stream_message(client, auth_headers):
    # 1. Create a trip
    trip_res = client.post("/api/v1/trips", json={"destination": "Berlin"}, headers=auth_headers)
    trip_id = trip_res.json()["id"]

    # 2. Post a message with stream=True
    response = client.post(
        f"/api/v1/trips/{trip_id}/messages?stream=true",
        json={"content": "Suggest historical sites for a 4 day vacation this summer with 1500 usd"},
        headers=auth_headers
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    
    # Read the streamed lines
    lines = [line if isinstance(line, str) else line.decode('utf-8') for line in response.iter_lines()]
    
    # Check that we have event stream items
    has_token = any("token" in line for line in lines)
    has_result = any("result" in line for line in lines)
    
    assert has_token
    assert has_result
