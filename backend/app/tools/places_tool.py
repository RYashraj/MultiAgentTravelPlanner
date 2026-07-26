from langchain_core.tools import tool
from typing import List, Dict, Any
import json

# Comprehensive mock data for major destinations to ensure a stunning demo
MOCK_PLACES_DB = {
    "Mumbai": [
        {"name": "Gateway of India", "type": "attraction", "rating": 4.6, "description": "Iconic waterfront monument built in the 20th century."},
        {"name": "Marine Drive", "type": "attraction", "rating": 4.8, "description": "3.6-km-long promenade along the Netaji Subhash Chandra Bose Road."},
        {"name": "Leopold Cafe", "type": "restaurant", "rating": 4.2, "description": "Historic restaurant and bar on Colaba Causeway."},
        {"name": "The Taj Mahal Palace", "type": "hotel", "rating": 4.9, "description": "Heritage, five-star, luxury hotel built in the Saracenic Revival style."}
    ],
    "Tokyo": [
        {"name": "Senso-ji Temple", "type": "attraction", "rating": 4.7, "description": "Tokyo's oldest Buddhist temple located in Asakusa."},
        {"name": "Shibuya Crossing", "type": "attraction", "rating": 4.6, "description": "The world's busiest pedestrian crossing."},
        {"name": "Ichiran Ramen", "type": "restaurant", "rating": 4.5, "description": "Famous tonkotsu ramen chain with private dining booths."},
        {"name": "Park Hyatt Tokyo", "type": "hotel", "rating": 4.8, "description": "Luxury hotel famous for its appearance in 'Lost in Translation'."}
    ],
    "Goa": [
        {"name": "Baga Beach", "type": "attraction", "rating": 4.2, "description": "Popular beach known for its water sports and nightlife."},
        {"name": "Basilica of Bom Jesus", "type": "attraction", "rating": 4.6, "description": "UNESCO World Heritage site containing the tomb of St. Francis Xavier."},
        {"name": "Britto's", "type": "restaurant", "rating": 4.1, "description": "Iconic beach shack famous for seafood and Goan cuisine."},
        {"name": "Taj Exotica", "type": "hotel", "rating": 4.8, "description": "Mediterranean-style 5-star resort located on Benaulim beach."}
    ]
}

@tool
def search_places(location: str, query_type: str) -> str:
    """
    Search for places, attractions, restaurants, or hotels in a given location.
    
    Args:
        location: The city or region (e.g., "Mumbai", "Tokyo").
        query_type: The type of place to search for (e.g., "attraction", "restaurant", "hotel", "all").
        
    Returns:
        A JSON string containing a list of places matching the criteria.
    """
    # Normalize input for matching
    loc_key = next((k for k in MOCK_PLACES_DB.keys() if k.lower() in location.lower()), None)
    
    if not loc_key:
        # Fallback generic data if location not in mock DB
        return json.dumps([
            {"name": f"Central Plaza in {location}", "type": "attraction", "rating": 4.5, "description": f"The beautiful central square of {location}."},
            {"name": f"{location} Grand Hotel", "type": "hotel", "rating": 4.7, "description": f"Luxurious stay in the heart of {location}."},
            {"name": f"Taste of {location}", "type": "restaurant", "rating": 4.4, "description": f"Authentic local cuisine in {location}."}
        ])
        
    places = MOCK_PLACES_DB[loc_key]
    
    if query_type.lower() != "all":
        places = [p for p in places if p["type"] == query_type.lower() or query_type.lower() in p["type"]]
        
    return json.dumps(places)
