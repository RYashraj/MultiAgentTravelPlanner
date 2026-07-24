"""Weather tool stub for Travel Planner."""


import logging
import httpx
from app.core.config import get_settings

logger = logging.getLogger(__name__)

def get_weather(destination: str, dates: str | None) -> dict:
    api_key = get_settings().openweather_api_key
    if not api_key:
        logger.warning("OpenWeather API key missing, falling back to mock weather data.")
        return {
            "destination": destination,
            "dates": dates,
            "temperature": "22°C",
            "condition": "Sunny with light clouds",
            "forecast": "Mild weather expected",
        }

    try:
        geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={destination}&limit=1&appid={api_key}"
        with httpx.Client(timeout=5.0) as client:
            geo_resp = client.get(geo_url)
            geo_resp.raise_for_status()
            geo_data = geo_resp.json()
            if not geo_data:
                return {"summary": f"Could not find coordinates for {destination}.", "warnings": []}
            
            lat, lon = geo_data[0]["lat"], geo_data[0]["lon"]
            
            weather_url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric"
            weather_resp = client.get(weather_url)
            weather_resp.raise_for_status()
            weather_data = weather_resp.json()
            
            condition = weather_data["weather"][0]["description"].capitalize() if weather_data.get("weather") else "Unknown"
            temp = f"{weather_data['main']['temp']}°C"
            
            return {
                "destination": destination,
                "dates": dates,
                "temperature": temp,
                "condition": condition,
                "forecast": f"{condition} with a temperature of {temp}.",
            }
    except Exception as e:
        logger.error(f"Error fetching weather for {destination}: {e}")
        return {
            "destination": destination,
            "dates": dates,
            "temperature": "Unknown",
            "condition": "Unknown",
            "forecast": f"Error fetching weather.",
        }
