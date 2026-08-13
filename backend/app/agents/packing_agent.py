"""
PackingAgent: Generates an intelligent packing list using Gemini, considering destination, duration, and weather.
Falls back to a generic list gracefully if the AI fails or data is missing.
"""
import logging
from typing import Any

from app.agents.gemini_client import call_gemini

logger = logging.getLogger(__name__)

def generate_packing_list(destination: str, duration_days: int, weather_data: dict[str, Any] | None) -> dict[str, Any]:
    """
    Generate a packing list based on trip parameters.
    Must never crash. Degrades gracefully to a generic list.
    """
    generic_list = {
        "status": "partial",
        "message": "Used generic packing list due to missing data or generation failure.",
        "categories": [
            {"name": "Essentials", "items": ["Passport/ID", "Wallet", "Phone & Charger", "Medications"]},
            {"name": "Clothing", "items": ["T-shirts", "Underwear", "Socks", "Pants/Shorts", "Light Jacket"]},
            {"name": "Toiletries", "items": ["Toothbrush", "Toothpaste", "Deodorant", "Shampoo", "Soap"]}
        ]
    }

    try:
        if not destination:
            return generic_list

        weather_str = "Unknown weather"
        if weather_data and isinstance(weather_data, dict):
            # Extract basic weather info if available
            condition = weather_data.get("condition", "unknown")
            temp = weather_data.get("temperature", "unknown")
            weather_str = f"{condition}, {temp}"
            
            # If weather is explicitly an error fallback
            if weather_data.get("source") == "error":
                weather_str = "Unknown weather"

        system_prompt = (
            "You are an expert travel assistant creating a concise, practical packing list.\n"
            "Return a JSON object matching this schema exactly:\n"
            "{\n"
            '  "status": "ok",\n'
            '  "categories": [\n'
            '    {"name": "Category Name (e.g., Clothing, Essentials)", "items": ["Item 1", "Item 2"]}\n'
            "  ]\n"
            "}\n"
            "Keep categories to 3-5, and items per category to 4-7. Tailor items to the destination, duration, and weather. "
            "If the destination or weather is extremely unusual or you are unsure, just provide a safe, generic list."
        )

        user_prompt = f"Destination: {destination}\nDuration: {duration_days} days\nWeather: {weather_str}"
        
        response = call_gemini(system_prompt, user_prompt, response_format="json")
        if not response:
            return generic_list
            
        import json
        data = json.loads(response)
        if "categories" in data and isinstance(data["categories"], list) and len(data["categories"]) > 0:
            return data
        else:
            return generic_list
            
    except Exception as exc:
        logger.warning(f"Packing list generation failed: {exc}")
        return generic_list
