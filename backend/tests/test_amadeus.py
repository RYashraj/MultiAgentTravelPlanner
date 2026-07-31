import json
import pytest
from unittest.mock import MagicMock, patch
import redis

from app.tools.amadeus_tool import (
    resolve_iata_code,
    get_fallback_flights,
    get_fallback_hotels,
    search_flights,
    search_hotels,
    get_amadeus_token,
    is_rate_limited
)
from app.core.config import get_settings

def test_resolve_iata_code():
    assert resolve_iata_code("Mumbai") == "BOM"
    assert resolve_iata_code("Delhi") == "DEL"
    assert resolve_iata_code("Goa, India") == "GOI"
    assert resolve_iata_code("Tokyo, Japan") == "TYO"
    assert resolve_iata_code("Paris") == "PAR"
    assert resolve_iata_code("London") == "LON"
    # Arbitrary strings fallback to uppercase first 3 letters
    assert resolve_iata_code("Berlin") == "BER"
    assert resolve_iata_code("Chicago") == "CHI"
    # Too short fallback
    assert resolve_iata_code("xy") == "BOM"

def test_get_fallback_flights():
    goa_flights = get_fallback_flights("BOM", "GOI")
    assert len(goa_flights) > 0
    assert goa_flights[0]["carrier"] == "IndiGo"
    assert "price" in goa_flights[0]

    generic_flights = get_fallback_flights("BOM", "XYZ")
    assert len(generic_flights) > 0
    assert generic_flights[0]["carrier"] == "IndiGo"

def test_get_fallback_hotels():
    goa_hotels = get_fallback_hotels("GOI")
    assert len(goa_hotels) > 0
    assert goa_hotels[0]["name"] == "Zostel Vagator Goa"

    generic_hotels = get_fallback_hotels("XYZ")
    assert len(generic_hotels) > 0
    assert "Budget Stay XYZ" in generic_hotels[0]["name"]

@patch("app.tools.amadeus_tool.get_amadeus_token")
def test_search_flights_fallback(mock_get_token):
    # If token is None, it should fall back to mock data
    mock_get_token.return_value = None
    res = search_flights.invoke({"origin": "Mumbai", "destination": "Goa", "departure_date": "2026-08-15"})
    data = json.loads(res)
    assert len(data) > 0
    assert data[0]["carrier"] == "IndiGo"

@patch("app.tools.amadeus_tool.get_amadeus_token")
def test_search_hotels_fallback(mock_get_token):
    mock_get_token.return_value = None
    res = search_hotels.invoke({"city": "Paris", "check_in_date": "2026-08-15", "check_out_date": "2026-08-22"})
    data = json.loads(res)
    assert len(data) > 0
    assert data[0]["name"] == "Generator Paris"

@patch("app.tools.amadeus_tool.get_redis_client")
def test_rate_limiting_mock_fallback(mock_get_redis):
    # Mock Redis client to simulate rate limit exceeded
    mock_client = MagicMock()
    mock_client.get.return_value = None  # Cache miss
    mock_client.incr.return_value = 11  # Exceeds the limit of 10
    mock_get_redis.return_value = mock_client

    assert is_rate_limited() is True

    # search_flights should fall back to mock data when rate limited
    with patch("app.tools.amadeus_tool.get_amadeus_token") as mock_get_token:
        mock_get_token.return_value = "fake_token"
        res = search_flights.invoke({"origin": "Mumbai", "destination": "Goa", "departure_date": "2026-08-15"})
        data = json.loads(res)
        assert len(data) > 0
        assert data[0]["carrier"] == "IndiGo"

@patch("app.tools.amadeus_tool.get_redis_client")
@patch("httpx.post")
def test_get_amadeus_token_caching(mock_post, mock_get_redis):
    # Test token fetching and caching
    settings = get_settings()
    settings.amadeus_api_key = "test_key"
    settings.amadeus_api_secret = "test_secret"

    mock_client = MagicMock()
    mock_client.get.return_value = None  # Cache miss
    mock_get_redis.return_value = mock_client

    # Mock HTTP response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "new_mocked_token",
        "expires_in": 1800
    }
    mock_post.return_value = mock_response

    token = get_amadeus_token()
    assert token == "new_mocked_token"
    mock_client.setex.assert_called_once_with("voyagerai:amadeus:token", 1500, "new_mocked_token")

    # Clean up settings
    settings.amadeus_api_key = ""
    settings.amadeus_api_secret = ""

@patch("app.tools.amadeus_tool.get_redis_client")
@patch("app.tools.amadeus_tool.get_amadeus_token")
@patch("httpx.get")
def test_search_flights_api_success(mock_get, mock_get_token, mock_get_redis):
    mock_get_token.return_value = "valid_token"
    mock_client = MagicMock()
    mock_client.get.return_value = None  # Cache miss
    mock_get_redis.return_value = mock_client

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [
            {
                "type": "flight-offer",
                "id": "1",
                "price": {"currency": "INR", "total": "4500.00"},
                "itineraries": [
                    {
                        "duration": "PT2H15M",
                        "segments": [
                            {
                                "carrierCode": "6E",
                                "number": "2035",
                                "departure": {"at": "2026-08-15T08:15:00"},
                                "arrival": {"at": "2026-08-15T10:30:00"}
                            }
                        ]
                    }
                ]
            }
        ]
    }
    mock_get.return_value = mock_response

    res = search_flights.invoke({"origin": "Mumbai", "destination": "Goa", "departure_date": "2026-08-15"})
    data = json.loads(res)
    assert len(data) == 1
    assert data[0]["carrier"] == "6E"
    assert data[0]["flight_number"] == "6E-2035"
    assert data[0]["price"] == "INR 4500.00"

    # Should cache result in Redis
    mock_client.setex.assert_called_once()
