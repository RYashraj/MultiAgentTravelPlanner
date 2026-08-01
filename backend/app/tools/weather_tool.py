import json

from langchain_core.tools import tool

MOCK_WEATHER_DB = {
    "Mumbai": {"temp": "32°C", "condition": "Sunny and Humid", "forecast": "Clear skies expected for the next 3 days."},
    "Tokyo": {"temp": "15°C", "condition": "Partly Cloudy", "forecast": "Chilly evenings, bring a light jacket."},
    "Goa": {"temp": "30°C", "condition": "Sunny", "forecast": "Perfect beach weather, no rain expected."}
}

@tool
def get_weather(location: str) -> str:
    """
    Get the current weather and short-term forecast for a location.
    
    Args:
        location: The city (e.g., "Mumbai").
        
    Returns:
        A JSON string containing weather information.
    """
    loc_key = next((k for k in MOCK_WEATHER_DB if k.lower() in location.lower()), None)
    
    if not loc_key:
        return json.dumps({"temp": "25°C", "condition": "Clear", "forecast": "Pleasant weather expected."})
        
    return json.dumps(MOCK_WEATHER_DB[loc_key])
