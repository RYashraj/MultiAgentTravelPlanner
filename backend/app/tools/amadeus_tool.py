import json
import logging
import time
import httpx
from langchain_core.tools import tool
from app.core.config import get_settings
from app.core.cache import get_session_cache

logger = logging.getLogger(__name__)

# --- IATA Code mappings for demo cities ---
CITY_TO_IATA = {
    "mumbai": "BOM",
    "bombay": "BOM",
    "delhi": "DEL",
    "new delhi": "DEL",
    "goa": "GOI",
    "panaji": "GOI",
    "tokyo": "TYO",
    "paris": "PAR",
    "london": "LON",
    "new york": "NYC",
    "nyc": "NYC",
    "berlin": "BER"
}

def resolve_iata_code(location_name: str) -> str:
    """Normalize input location to IATA code."""
    loc_clean = location_name.strip().lower()
    for name, iata in CITY_TO_IATA.items():
        if name in loc_clean or loc_clean in name:
            return iata
    # Default fallback: return first 3 characters capitalized
    clean_code = "".join(filter(str.isalpha, loc_clean))
    return clean_code[:3].upper() if len(clean_code) >= 3 else "BOM"

# --- Mock Fallback Data ---
MOCK_FLIGHTS = {
    "GOI": [
        {"carrier": "IndiGo", "flight_number": "6E-2035", "departure_time": "08:15", "arrival_time": "10:30", "price": "₹4,200", "duration": "2h 15m", "cabin": "Economy"},
        {"carrier": "Air India", "flight_number": "AI-867", "departure_time": "14:00", "arrival_time": "16:15", "price": "₹4,800", "duration": "2h 15m", "cabin": "Economy"},
        {"carrier": "Akasa Air", "flight_number": "QP-1102", "departure_time": "18:30", "arrival_time": "20:45", "price": "₹3,900", "duration": "2h 15m", "cabin": "Economy"}
    ],
    "DEL": [
        {"carrier": "Vistara", "flight_number": "UK-985", "departure_time": "07:30", "arrival_time": "09:40", "price": "₹5,400", "duration": "2h 10m", "cabin": "Economy"},
        {"carrier": "IndiGo", "flight_number": "6E-5312", "departure_time": "12:15", "arrival_time": "14:30", "price": "₹4,500", "duration": "2h 15m", "cabin": "Economy"},
        {"carrier": "Air India", "flight_number": "AI-805", "departure_time": "19:00", "arrival_time": "21:15", "price": "₹5,200", "duration": "2h 15m", "cabin": "Economy"}
    ],
    "TYO": [
        {"carrier": "Japan Airlines", "flight_number": "JL-742", "departure_time": "19:15", "arrival_time": "06:30 (+1)", "price": "¥85,000", "duration": "8h 15m", "cabin": "Economy"},
        {"carrier": "All Nippon Airways", "flight_number": "NH-830", "departure_time": "22:00", "arrival_time": "09:15 (+1)", "price": "¥92,000", "duration": "8h 15m", "cabin": "Economy"},
        {"carrier": "Singapore Airlines", "flight_number": "SQ-638", "departure_time": "11:30", "arrival_time": "21:45", "price": "¥78,000", "duration": "10h 15m (1 stop)", "cabin": "Economy"}
    ],
    "PAR": [
        {"carrier": "Air France", "flight_number": "AF-225", "departure_time": "12:45", "arrival_time": "18:30", "price": "€650", "duration": "9h 45m", "cabin": "Economy"},
        {"carrier": "Emirates", "flight_number": "EK-501", "departure_time": "14:15", "arrival_time": "23:55", "price": "€580", "duration": "12h 40m (1 stop)", "cabin": "Economy"},
        {"carrier": "Gulf Air", "flight_number": "GF-056", "departure_time": "05:30", "arrival_time": "14:45", "price": "€490", "duration": "12h 15m (1 stop)", "cabin": "Economy"}
    ],
    "BOM": [
        {"carrier": "IndiGo", "flight_number": "6E-5301", "departure_time": "06:00", "arrival_time": "08:15", "price": "₹4,100", "duration": "2h 15m", "cabin": "Economy"},
        {"carrier": "Vistara", "flight_number": "UK-930", "departure_time": "17:30", "arrival_time": "19:45", "price": "₹5,300", "duration": "2h 15m", "cabin": "Economy"}
    ],
    "LON": [
        {"carrier": "British Airways", "flight_number": "BA-138", "departure_time": "13:15", "arrival_time": "18:45", "price": "£550", "duration": "9h 30m", "cabin": "Economy"},
        {"carrier": "Virgin Atlantic", "flight_number": "VS-351", "departure_time": "10:30", "arrival_time": "16:00", "price": "£580", "duration": "9h 30m", "cabin": "Economy"},
        {"carrier": "Qatar Airways", "flight_number": "QR-008", "departure_time": "04:15", "arrival_time": "13:30", "price": "£480", "duration": "12h 15m (1 stop)", "cabin": "Economy"}
    ]
}

MOCK_HOTELS = {
    "GOI": [
        {"name": "Zostel Vagator Goa", "price_per_night": "₹800", "currency": "INR", "room_type": "Dorm Bed", "description": "Backpacker hostel near Vagator beach, social vibe, pool, cafe."},
        {"name": "Hotel ibis Styles Goa Calangute", "price_per_night": "₹4,500", "currency": "INR", "room_type": "Standard Double Room", "description": "Vibrant design, near Calangute beach, 2 swimming pools, gym."},
        {"name": "Taj Exotica Resort & Spa Goa", "price_per_night": "₹22,000", "currency": "INR", "room_type": "Villa Garden View", "description": "Mediterranean-style luxury resort on Benaulim Beach, private beach access, spa."}
    ],
    "DEL": [
        {"name": "Zostel Delhi", "price_per_night": "₹650", "currency": "INR", "room_type": "Dorm Bed", "description": "Backpacker hostel in central Delhi, rooftop terrace, clean, vibrant common area."},
        {"name": "Bloomrooms @ Link Road", "price_per_night": "₹3,800", "currency": "INR", "room_type": "Standard Room", "description": "Award-winning yellow-themed boutique hotel, highly rated cleanliness, cafe, near metro."},
        {"name": "The Leela Palace New Delhi", "price_per_night": "₹18,500", "currency": "INR", "room_type": "Grande Deluxe Room", "description": "Palatial 5-star luxury in Chanakyapuri, rooftop infinity pool, fine dining."}
    ],
    "TYO": [
        {"name": "Khaosan Tokyo Origami", "price_per_night": "¥3,500", "currency": "JPY", "room_type": "Dormitory Bed", "description": "Cozy hostel in Asakusa near Senso-ji temple, traditional art gallery theme, shared kitchen."},
        {"name": "Hotel Sunroute Plaza Shinjuku", "price_per_night": "¥14,000", "currency": "JPY", "room_type": "Standard Twin Room", "description": "Modern hotel 3 mins walk from Shinjuku station, ideal location, free Wi-Fi."},
        {"name": "Park Hyatt Tokyo", "price_per_night": "¥65,000", "currency": "JPY", "room_type": "Park Deluxe Room", "description": "Iconic luxury hotel in Shinjuku, panoramic city views, fine dining."}
    ],
    "PAR": [
        {"name": "St Christopher's Inn Paris Canal", "price_per_night": "€35", "currency": "EUR", "room_type": "Dorm Bed", "description": "Modern waterfront hostel, Belushi's bar, terrace, near Gare du Nord."},
        {"name": "Novotel Paris Les Halles", "price_per_night": "€180", "currency": "EUR", "room_type": "Executive Room", "description": "Central Paris location near Louvre, patio dining, modern fitness center."},
        {"name": "The Ritz Paris", "price_per_night": "€1,200", "currency": "EUR", "room_type": "Deluxe Suite", "description": "Legendary luxury hotel on Place Vendôme, Michelin-starred dining, spa."}
    ],
    "BOM": [
        {"name": "Zostel Mumbai (Colaba)", "price_per_night": "₹900", "currency": "INR", "room_type": "Dorm Bed", "description": "Vibrant backpacker hostel in South Mumbai, near Gateway of India."},
        {"name": "Ibis Mumbai Vikhroli", "price_per_night": "₹4,200", "currency": "INR", "room_type": "Standard Room", "description": "Modern, well-connected hotel in central Mumbai with high-speed WiFi."},
        {"name": "The Taj Mahal Palace Mumbai", "price_per_night": "₹24,000", "currency": "INR", "room_type": "Luxury Grand Room", "description": "World-famous luxury heritage hotel overlooking the Gateway of India."}
    ],
    "LON": [
        {"name": "Generator Hostel London", "price_per_night": "£30", "currency": "GBP", "room_type": "Dorm Bed", "description": "Stylish hostel near Russell Square and Covent Garden, bar, games room."},
        {"name": "CitizenM Tower of London", "price_per_night": "£140", "currency": "GBP", "room_type": "King Room", "description": "Boutique technology-driven hotel with skyline views of Tower Bridge."},
        {"name": "The Savoy", "price_per_night": "£750", "currency": "GBP", "room_type": "Luxury King Room", "description": "Iconic British luxury hotel on the Strand, Gordon Ramsay restaurant."}
    ]
}

# Token Cache
_token_cache = {"access_token": None, "expires_at": 0}

def get_amadeus_access_token() -> str | None:
    """Fetch OAuth2 token from Amadeus Test API."""
    now = time.time()
    if _token_cache["access_token"] and _token_cache["expires_at"] > now:
        return _token_cache["access_token"]
    
    settings = get_settings()
    api_key = settings.amadeus_api_key
    api_secret = settings.amadeus_api_secret

    if not api_key or not api_secret:
        logger.info("Amadeus API key/secret missing. Using mock data fallback.")
        return None

    try:
        url = "https://test.api.amadeus.com/v1/security/oauth2/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "client_credentials",
            "client_id": api_key,
            "client_secret": api_secret
        }
        with httpx.Client(timeout=5.0) as client:
            res = client.post(url, headers=headers, data=data)
            if res.status_code == 200:
                res_data = res.json()
                _token_cache["access_token"] = res_data["access_token"]
                _token_cache["expires_at"] = now + res_data.get("expires_in", 1799) - 60
                return _token_cache["access_token"]
            else:
                logger.warning("Amadeus Auth failed [%d]: %s", res.status_code, res.text)
    except Exception as e:
        logger.warning("Amadeus Auth exception: %s. Using mock fallback.", e)
    
    return None

@tool
def search_flights(origin: str, destination: str, date: str | None = None) -> str:
    """
    Search for flights between origin and destination.
    
    Args:
        origin: Departure city or IATA code (e.g. "Mumbai" or "BOM")
        destination: Arrival city or IATA code (e.g. "Goa" or "GOI")
        date: Travel date in YYYY-MM-DD format (optional)
        
    Returns:
        JSON string containing flight offers.
    """
    orig_code = resolve_iata_code(origin)
    dest_code = resolve_iata_code(destination)
    
    token = get_amadeus_access_token()
    if token:
        try:
            url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
            headers = {"Authorization": f"Bearer {token}"}
            travel_date = date if date and len(date) == 10 else "2025-06-15"
            params = {
                "originLocationCode": orig_code,
                "destinationLocationCode": dest_code,
                "departureDate": travel_date,
                "adults": 1,
                "max": 3
            }
            with httpx.Client(timeout=8.0) as client:
                res = client.get(url, headers=headers, params=params)
                if res.status_code == 200:
                    data = res.json()
                    offers = []
                    for item in data.get("data", []):
                        price_val = item.get("price", {}).get("total", "N/A")
                        currency = item.get("price", {}).get("currency", "EUR")
                        itins = item.get("itineraries", [{}])[0]
                        duration = itins.get("duration", "N/A").replace("PT", "").lower()
                        segment = itins.get("segments", [{}])[0]
                        carrier = segment.get("carrierCode", "Airline")
                        number = segment.get("number", "101")
                        dep_time = segment.get("departure", {}).get("at", "").split("T")[-1][:5]
                        arr_time = segment.get("arrival", {}).get("at", "").split("T")[-1][:5]
                        
                        offers.append({
                            "carrier": carrier,
                            "flight_number": f"{carrier}-{number}",
                            "departure_time": dep_time or "09:00",
                            "arrival_time": arr_time or "11:15",
                            "price": f"{currency} {price_val}",
                            "duration": duration,
                            "cabin": "Economy"
                        })
                    if offers:
                        return json.dumps(offers)
        except Exception as e:
            logger.warning("Amadeus live flight search failed (%s). Using mock fallback.", e)
            
    # Mock Fallback
    flights = MOCK_FLIGHTS.get(dest_code) or MOCK_FLIGHTS.get("GOI", [])
    return json.dumps(flights)

@tool
def search_hotels(location: str, check_in: str | None = None, check_out: str | None = None, budget_tier: str = "midrange") -> str:
    """
    Search for hotels in a destination matching budget tier.
    
    Args:
        location: Destination city or IATA code (e.g. "Delhi" or "DEL")
        check_in: Check-in date YYYY-MM-DD (optional)
        check_out: Check-out date YYYY-MM-DD (optional)
        budget_tier: "budget", "midrange", or "luxury"
        
    Returns:
        JSON string containing hotel options.
    """
    dest_code = resolve_iata_code(location)
    
    token = get_amadeus_access_token()
    if token:
        try:
            # 1. Search hotel list by city code
            url_list = "https://test.api.amadeus.com/v1/reference-data/locations/hotels/by-city"
            headers = {"Authorization": f"Bearer {token}"}
            params_list = {"cityCode": dest_code}
            with httpx.Client(timeout=8.0) as client:
                res_list = client.get(url_list, headers=headers, params=params_list)
                if res_list.status_code == 200:
                    data_list = res_list.json().get("data", [])
                    if data_list:
                        hotel_ids = [h["hotelId"] for h in data_list[:3]]
                        url_offers = "https://test.api.amadeus.com/v3/shopping/hotel-offers"
                        c_in = check_in if check_in and len(check_in) == 10 else "2025-06-15"
                        c_out = check_out if check_out and len(check_out) == 10 else "2025-06-18"
                        params_offers = {
                            "hotelIds": ",".join(hotel_ids),
                            "checkInDate": c_in,
                            "checkOutDate": c_out,
                            "adults": 1
                        }
                        res_offers = client.get(url_offers, headers=headers, params=params_offers)
                        if res_offers.status_code == 200:
                            offers_data = res_offers.json().get("data", [])
                            hotels = []
                            for h_item in offers_data:
                                h_name = h_item.get("hotel", {}).get("name", "Local Hotel")
                                offer = h_item.get("offers", [{}])[0]
                                p_val = offer.get("price", {}).get("total", "N/A")
                                curr = offer.get("price", {}).get("currency", "EUR")
                                r_type = offer.get("room", {}).get("typeEstimated", {}).get("category", "Standard Room")
                                hotels.append({
                                    "name": h_name,
                                    "price_per_night": f"{curr} {p_val}",
                                    "currency": curr,
                                    "room_type": r_type,
                                    "description": f"Hotel near center of {location}."
                                })
                            if hotels:
                                return json.dumps(hotels)
        except Exception as e:
            logger.warning("Amadeus live hotel search failed (%s). Using mock fallback.", e)
            
    # Mock Fallback
    hotels = MOCK_HOTELS.get(dest_code) or MOCK_HOTELS.get("GOI", [])
    
    # Filter by budget tier if mock data contains varied options
    if budget_tier == "budget":
        filtered = [h for h in hotels if any(w in h["description"].lower() or w in h["room_type"].lower() for w in ["hostel", "dorm", "backpacker", "zostel", "st christopher"])]
    elif budget_tier == "luxury":
        filtered = [h for h in hotels if any(w in h["description"].lower() or w in h["name"].lower() for w in ["resort", "palace", "ritz", "savoy", "taj", "luxury", "5-star"])]
    else: # midrange
        filtered = [h for h in hotels if not any(w in h["description"].lower() for w in ["hostel", "dorm"]) and not any(w in h["name"].lower() for w in ["ritz", "savoy", "palace"])]
        
    return json.dumps(filtered if filtered else hotels)
