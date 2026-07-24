"""Places/Attractions tool stub for Travel Planner."""


import logging
import httpx
from app.core.config import get_settings

logger = logging.getLogger(__name__)

def search_attractions(destination: str, preferences: list[str]) -> list[dict]:
    api_key = get_settings().google_places_api_key
    if not api_key:
        logger.warning("Google Places API key missing, falling back to mock attraction data.")
        return [
            {
                "name": f"Famous Sight in {destination}",
                "category": preferences[0] if preferences else "Sightseeing",
                "rating": 4.8,
                "description": f"Top-rated destination in {destination}.",
            },
            {
                "name": f"Local Park in {destination}",
                "category": "Nature",
                "rating": 4.5,
                "description": f"Beautiful nature spot in {destination}.",
            },
        ]

    try:
        query = f"top attractions in {destination}"
        if preferences:
            query = f"{', '.join(preferences)} in {destination}"
            
        url = "https://places.googleapis.com/v1/places:searchText"
        headers = {
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.rating,places.editorialSummary,places.primaryType",
            "Content-Type": "application/json",
        }
        payload = {
            "textQuery": query,
            "maxResultCount": 5
        }
        
        with httpx.Client(timeout=8.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            
            attractions = []
            for place in data.get("places", []):
                attractions.append({
                    "name": place.get("displayName", {}).get("text", "Unknown Attraction"),
                    "category": place.get("primaryType", "Sightseeing"),
                    "rating": place.get("rating", 0.0),
                    "description": place.get("editorialSummary", {}).get("text", f"Attraction in {destination}."),
                })
            
            return attractions
    except Exception as e:
        logger.error(f"Error fetching places for {destination}: {e}")
        return []
