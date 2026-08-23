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

        user_prompt = (
            f"Destination: {destination}\n"
            f"Duration: {duration_days} days\n"
            f"Current weather: {weather_str}\n\n"
            f"RULES:\n"
            f"1. Use the EXACT destination name '{destination}' in category headers or item notes where relevant.\n"
            f"2. The clothing category MUST reflect the actual weather ({weather_str}) — not generic items.\n"
            f"   e.g., if hot: sunscreen, light fabrics; if cold: layers, thermals; if rainy: waterproof jacket.\n"
            f"3. Include at least one {destination}-specific item if applicable "
            f"(e.g., 'sturdy shoes for cobblestone Old Delhi lanes', 'water shoes for Goa beaches', "
            f"'altitude sickness pills for Manali trekking').\n"
            f"4. For a {duration_days}-day trip, recommend appropriate quantities "
            f"(e.g., '{duration_days} sets of clothing', 'enough medication for {duration_days}+ days').\n"
            f"Return ONLY the JSON object — no markdown, no extra text."
        )
        
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
