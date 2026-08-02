"""
weather_tool.py — AI-powered weather tool using OpenWeatherMap API with Gemini fallback.

Design:
  - PRIMARY: Calls OpenWeatherMap API for real current weather data.
  - SECONDARY: If OPENWEATHER_API_KEY unavailable, uses Gemini to estimate typical weather.
  - FALLBACK: Static mock data for demo reliability if both above fail.
"""
import json
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

MOCK_WEATHER_DB = {
    "Mumbai": {"temp": "32°C", "condition": "Sunny and Humid", "forecast": "Clear skies expected for the next 3 days."},
    "Tokyo": {"temp": "15°C", "condition": "Partly Cloudy", "forecast": "Chilly evenings, bring a light jacket."},
    "Goa": {"temp": "30°C", "condition": "Sunny", "forecast": "Perfect beach weather, no rain expected."},
    "Delhi": {"temp": "38°C", "condition": "Hot and Hazy", "forecast": "Very hot days, stay hydrated. Evenings slightly cooler."},
    "Jaipur": {"temp": "36°C", "condition": "Hot and Dry", "forecast": "Extremely hot afternoons. Best to sightsee mornings and evenings."},
    "Bangalore": {"temp": "24°C", "condition": "Pleasant and Breezy", "forecast": "Comfortable weather, occasional evening showers."},
    "London": {"temp": "16°C", "condition": "Overcast", "forecast": "Typical British weather — carry an umbrella."},
    "Paris": {"temp": "18°C", "condition": "Mild and Sunny", "forecast": "Beautiful weather for sightseeing."},
    "New York": {"temp": "22°C", "condition": "Clear", "forecast": "Great weather for exploring the city."},
    "Dubai": {"temp": "40°C", "condition": "Very Hot and Sunny", "forecast": "Extremely hot — stay indoors during peak afternoon hours."},
}


def _fetch_openweather(location: str) -> dict | None:
    """Fetch live weather data from OpenWeatherMap API."""
    try:
        from app.core.config import get_settings
        settings = get_settings()
        api_key = getattr(settings, "openweather_api_key", None)
        if not api_key:
            return None

        import httpx
        url = f"https://api.openweathermap.org/data/2.5/weather?q={location}&appid={api_key}&units=metric"
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                temp_c = round(data["main"]["temp"])
                condition = data["weather"][0]["description"].title()
                humidity = data["main"]["humidity"]
                feels_like = round(data["main"]["feels_like"])
                return {
                    "temp": f"{temp_c}°C",
                    "condition": condition,
                    "humidity": f"{humidity}%",
                    "feels_like": f"{feels_like}°C",
                    "forecast": (
                        f"Current: {temp_c}°C, feels like {feels_like}°C. "
                        f"Humidity: {humidity}%. {condition}."
                    ),
                    "source": "openweathermap",
                }
    except Exception as exc:
        logger.debug("OpenWeatherMap API call failed: %s", exc)
    return None


def _fetch_gemini_weather(location: str) -> dict | None:
    """Use Gemini to provide typical weather context for a destination."""
    try:
        from app.agents.gemini_client import call_gemini
        from langchain_core.messages import HumanMessage, SystemMessage

        import datetime
        current_month = datetime.datetime.now().strftime("%B")

        messages = [
            SystemMessage(content=(
                "You are a weather expert for the VoyagerAI travel system. "
                "Provide typical weather information for a destination in the current month. "
                "Respond ONLY with a valid JSON object (no markdown, no code blocks) with:\n"
                "- temp: string (typical temperature, e.g. '28°C')\n"
                "- condition: string (typical weather condition)\n"
                "- humidity: string (typical humidity, e.g. '70%')\n"
                "- forecast: string (2-3 sentence weather summary and travel tips for this season)\n"
                "- packing_tips: string (what to pack for this weather)\n"
                "Be specific and accurate based on real climatological knowledge."
            )),
            HumanMessage(content=(
                f"What is the typical weather in {location} during {current_month}? "
                f"Provide accurate weather information a traveller needs to know."
            )),
        ]

        raw = call_gemini(messages, timeout=10)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(line for line in lines if not line.startswith("```")).strip()

        parsed = json.loads(cleaned)
        return {
            "temp": str(parsed.get("temp", "25°C")),
            "condition": str(parsed.get("condition", "Mild")),
            "humidity": str(parsed.get("humidity", "")),
            "forecast": str(parsed.get("forecast", "")),
            "packing_tips": str(parsed.get("packing_tips", "")),
            "source": "ai_seasonal",
        }

    except Exception as exc:
        logger.debug("Gemini weather estimation failed: %s", exc)
    return None


@tool
def get_weather(location: str) -> str:
    """
    Get the current weather and short-term forecast for a location.

    Tries OpenWeatherMap API first, then Gemini AI seasonal estimate, then mock data.

    Args:
        location: The city name (e.g., "Mumbai", "Tokyo", "London").

    Returns:
        A JSON string containing weather information.
    """
    # Step 1: Try real OpenWeatherMap API
    live_data = _fetch_openweather(location)
    if live_data:
        logger.info("WeatherAgent: Live weather data fetched for %s", location)
        return json.dumps(live_data)

    # Step 2: Try Gemini AI seasonal estimate
    ai_data = _fetch_gemini_weather(location)
    if ai_data:
        logger.info("WeatherAgent: AI seasonal weather estimated for %s", location)
        return json.dumps(ai_data)

    # Step 3: Fall back to mock data
    loc_key = next((k for k in MOCK_WEATHER_DB if k.lower() in location.lower()), None)
    if loc_key:
        mock = MOCK_WEATHER_DB[loc_key].copy()
        mock["source"] = "mock"
        return json.dumps(mock)

    # Generic fallback
    return json.dumps({
        "temp": "25°C",
        "condition": "Clear and Pleasant",
        "forecast": f"Weather in {location} is generally pleasant for travel. Check a weather app for live updates.",
        "source": "generic",
    })
