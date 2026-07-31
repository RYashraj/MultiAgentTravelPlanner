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
        {"name": "Hotel Sunroute Plaza Shinjuku", "price_per_night": "¥14,000", "currency": "JPY", "room_type": "Standard Double", "description": "Comfortable mid-range hotel next to Shinjuku Station, convenient airport bus, spa, massage."},
        {"name": "Park Hyatt Tokyo", "price_per_night": "¥75,000", "currency": "JPY", "room_type": "Park Deluxe Room", "description": "Ultra-luxury hotel in Shinjuku, stunning Mount Fuji views, indoor pool, Peak Lounge."}
    ],
    "PAR": [
        {"name": "Generator Paris", "price_per_night": "€35", "currency": "EUR", "room_type": "Shared Dorm Bed", "description": "Designer hostel in 10th Arrondissement, canal view, rooftop bar, social events."},
        {"name": "Hotel ibis Paris Tour Eiffel", "price_per_night": "€95", "currency": "EUR", "room_type": "Standard Room with Double Bed", "description": "Reliable mid-range hotel near Eiffel Tower, breakfast buffet, 24/7 bar, friendly staff."},
        {"name": "Shangri-La Paris", "price_per_night": "€950", "currency": "EUR", "room_type": "Deluxe Room", "description": "Palace hotel in former residence of Prince Roland Bonaparte, Michelin dining, direct Eiffel views."}
    ],
    "BOM": [
        {"name": "Zostel Mumbai", "price_per_night": "₹750", "currency": "INR", "room_type": "Dorm Bed", "description": "Hostel in Andheri East, social events, cafe, library, easy transit access."},
        {"name": "Hotel Suba Palace", "price_per_night": "₹4,200", "currency": "INR", "room_type": "Executive Double Room", "description": "Highly rated boutique hotel near Gateway of India, breakfast buffet, modern decor."},
        {"name": "The Taj Mahal Palace Mumbai", "price_per_night": "₹24,000", "currency": "INR", "room_type": "Superior Room Tower", "description": "World-famous heritage hotel overlooking the Arabian Sea and Gateway of India, luxury dining."}
    ],
    "LON": [
        {"name": "SoHostel London", "price_per_night": "£30", "currency": "GBP", "room_type": "Dorm Bed", "description": "Stylish budget hostel in Soho, central location, bar, close to Oxford Street shops."},
        {"name": "CitizenM London Bankside", "price_per_night": "£130", "currency": "GBP", "room_type": "Standard Double", "description": "Chic boutique hotel near Tate Modern, tablet-controlled rooms, 24/7 canteen, cool design."},
        {"name": "The Savoy", "price_per_night": "£650", "currency": "GBP", "room_type": "Deluxe King Room", "description": "Iconic luxury hotel on the Strand, Edwardian design, butler service, world-class American Bar."}
    ]
}

def get_fallback_flights(origin_iata: str, destination_iata: str) -> list:
    """Retrieve fallback flight data for demo locations."""
    mock_list = MOCK_FLIGHTS.get(destination_iata)
    if mock_list:
        return mock_list
    # Generate generic mock flight
    return [
        {"carrier": "IndiGo", "flight_number": "6E-101", "departure_time": "09:00", "arrival_time": "11:30", "price": "₹5,000", "duration": "2h 30m", "cabin": "Economy"},
        {"carrier": "Air India", "flight_number": "AI-202", "departure_time": "15:00", "arrival_time": "17:30", "price": "₹6,000", "duration": "2h 30m", "cabin": "Economy"}
    ]

def get_fallback_hotels(city_iata: str) -> list:
    """Retrieve fallback hotel data for demo locations."""
    mock_list = MOCK_HOTELS.get(city_iata)
    if mock_list:
        return mock_list
    # Generic mock hotels
    return [
        {"name": f"Budget Stay {city_iata}", "price_per_night": "₹1,500", "currency": "INR", "room_type": "Standard Room", "description": "Clean budget lodging with essential amenities."},
        {"name": f"Central Plaza Hotel {city_iata}", "price_per_night": "₹4,500", "currency": "INR", "room_type": "Deluxe Room", "description": "Mid-range hotel with complimentary breakfast and central location."},
        {"name": f"Grand Palace Resort {city_iata}", "price_per_night": "₹15,000", "currency": "INR", "room_type": "Suite Room", "description": "Premium 5-star experience, swimming pool, luxury dining options."}
    ]

# --- Redis Cache & Rate Limit Helpers ---
def get_redis_client():
    """Fail-safe Redis client fetcher."""
    try:
        return get_session_cache().client
    except Exception:
        return None

def is_rate_limited() -> bool:
    """Fixed-window rate limiting (max 10 requests per minute overall)."""
    client = get_redis_client()
    if not client:
        return False
    try:
        now_bucket = int(time.time()) // 60
        key = f"voyagerai:ratelimit:amadeus:{now_bucket}"
        current = client.incr(key)
        if current == 1:
            client.expire(key, 120)
        return current > 10
    except Exception as exc:
        logger.warning("Redis rate limiter error: %s", exc)
        return False

# --- Amadeus API Token Helper ---
def get_amadeus_token() -> str | None:
    """Fetches or returns cached access token for Amadeus API."""
    settings = get_settings()
    api_key = settings.amadeus_api_key
    api_secret = settings.amadeus_api_secret

    if not api_key or not api_secret:
        logger.debug("Amadeus API key or secret missing from environment configuration.")
        return None

    client = get_redis_client()
    if client:
        try:
            cached_token = client.get("voyagerai:amadeus:token")
            if cached_token:
                return cached_token
        except Exception as exc:
            logger.warning("Failed to fetch cached Amadeus token: %s", exc)

    # Fetch new token from Amadeus Security API
    try:
        url = "https://test.api.amadeus.com/v1/security/oauth2/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "client_credentials",
            "client_id": api_key,
            "client_secret": api_secret
        }
        res = httpx.post(url, headers=headers, data=data, timeout=5.0)
        if res.status_code == 200:
            token_data = res.json()
            access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 1799)
            if access_token and client:
                try:
                    # Cache the token slightly shorter than the official expiry
                    cache_ttl = max(60, expires_in - 300)
                    client.setex("voyagerai:amadeus:token", cache_ttl, access_token)
                except Exception as exc:
                    logger.warning("Failed to cache Amadeus token: %s", exc)
            return access_token
        else:
            logger.error("Amadeus OAuth2 request failed: %d %s", res.status_code, res.text)
            return None
    except Exception as exc:
        logger.exception("Exception occurred during Amadeus token retrieval: %s", exc)
        return None

# --- LangChain Registered Tools ---
@tool
def search_flights(origin: str, destination: str, departure_date: str, return_date: str = None) -> str:
    """
    Search for available flights using the Amadeus Search API.
    
    Args:
        origin: The departure city name or 3-letter IATA code (e.g. "Mumbai" or "BOM").
        destination: The arrival city name or 3-letter IATA code (e.g. "Goa" or "GOI").
        departure_date: Date of departure in YYYY-MM-DD format.
        return_date: Optional return date in YYYY-MM-DD format (for roundtrip).
        
    Returns:
        A JSON string listing the top available flight offers.
    """
    origin_iata = resolve_iata_code(origin)
    destination_iata = resolve_iata_code(destination)
    dep_clean = departure_date.strip()
    ret_clean = return_date.strip() if return_date else ""

    # Build cache key
    cache_key = f"voyagerai:cache:amadeus:flights:{origin_iata}:{destination_iata}:{dep_clean}:{ret_clean or 'oneway'}"
    client = get_redis_client()

    if client:
        try:
            cached_data = client.get(cache_key)
            if cached_data:
                logger.info("Amadeus Flight Search: cache hit for %s -> %s", origin_iata, destination_iata)
                return cached_data
        except Exception as exc:
            logger.warning("Cache retrieval error: %s", exc)

    # Check Rate Limiting
    if is_rate_limited():
        logger.warning("Amadeus Flight Search: Rate limited. Falling back to mock data.")
        return json.dumps(get_fallback_flights(origin_iata, destination_iata))

    # Obtain Access Token
    token = get_amadeus_token()
    if not token:
        logger.info("Amadeus Access Token unavailable. Falling back to mock data.")
        return json.dumps(get_fallback_flights(origin_iata, destination_iata))

    # Query API
    try:
        url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "originLocationCode": origin_iata,
            "destinationLocationCode": destination_iata,
            "departureDate": dep_clean,
            "adults": 1,
            "max": 5
        }
        if ret_clean:
            params["returnDate"] = ret_clean

        res = httpx.get(url, headers=headers, params=params, timeout=5.0)
        if res.status_code == 200:
            raw_offers = res.json().get("data", [])
            clean_offers = []
            
            # Map raw Amadeus offers into lightweight structures
            for offer in raw_offers[:5]:
                price_info = offer.get("price", {})
                price_str = f"{price_info.get('currency', 'EUR')} {price_info.get('total', 'N/A')}"
                
                # Fetch first segment details
                itineraries = offer.get("itineraries", [])
                if not itineraries:
                    continue
                first_itinerary = itineraries[0]
                duration_str = first_itinerary.get("duration", "").replace("PT", "").lower()
                segments = first_itinerary.get("segments", [])
                if not segments:
                    continue
                first_seg = segments[0]
                carrier_code = first_seg.get("carrierCode", "N/A")
                flight_num = f"{carrier_code}-{first_seg.get('number', 'N/A')}"
                dep_time = first_seg.get("departure", {}).get("at", "").split("T")[-1][:5]
                arr_time = segments[-1].get("arrival", {}).get("at", "").split("T")[-1][:5]
                
                clean_offers.append({
                    "carrier": carrier_code,
                    "flight_number": flight_num,
                    "departure_time": dep_time,
                    "arrival_time": arr_time,
                    "price": price_str,
                    "duration": duration_str,
                    "cabin": "Economy"
                })

            if not clean_offers:
                logger.warning("Real Amadeus Flight Search returned empty offers. Loading fallback data.")
                clean_offers = get_fallback_flights(origin_iata, destination_iata)

            # Save in Redis cache
            result_json = json.dumps(clean_offers)
            if client:
                try:
                    client.setex(cache_key, 3600, result_json)
                except Exception as exc:
                    logger.warning("Cache write error: %s", exc)

            return result_json
        else:
            logger.error("Amadeus Flight Search API responded with status %d: %s", res.status_code, res.text)
            return json.dumps(get_fallback_flights(origin_iata, destination_iata))

    except Exception as exc:
        logger.exception("Amadeus Flight Search exception occurred: %s", exc)
        return json.dumps(get_fallback_flights(origin_iata, destination_iata))


@tool
def search_hotels(city: str, check_in_date: str, check_out_date: str) -> str:
    """
    Search for hotels and availability using the Amadeus reference and shopping v3 APIs.
    
    Args:
        city: City name or 3-letter IATA code (e.g. "Paris" or "PAR").
        check_in_date: Check-in date in YYYY-MM-DD format.
        check_out_date: Check-out date in YYYY-MM-DD format.
        
    Returns:
        A JSON string listing the available hotel offers.
    """
    city_iata = resolve_iata_code(city)
    check_in = check_in_date.strip()
    check_out = check_out_date.strip()

    cache_key = f"voyagerai:cache:amadeus:hotels:{city_iata}:{check_in}:{check_out}"
    client = get_redis_client()

    if client:
        try:
            cached_data = client.get(cache_key)
            if cached_data:
                logger.info("Amadeus Hotel Search: cache hit for %s", city_iata)
                return cached_data
        except Exception as exc:
            logger.warning("Cache retrieval error: %s", exc)

    # Check Rate Limiting
    if is_rate_limited():
        logger.warning("Amadeus Hotel Search: Rate limited. Falling back to mock data.")
        return json.dumps(get_fallback_hotels(city_iata))

    # Obtain Access Token
    token = get_amadeus_token()
    if not token:
        logger.info("Amadeus Access Token unavailable. Falling back to mock data.")
        return json.dumps(get_fallback_hotels(city_iata))

    # Query v1 reference-data to get hotel IDs for the city
    try:
        list_url = "https://test.api.amadeus.com/v1/reference-data/locations/hotels/by-city"
        headers = {"Authorization": f"Bearer {token}"}
        list_params = {"cityCode": city_iata}
        
        list_res = httpx.get(list_url, headers=headers, params=list_params, timeout=5.0)
        if list_res.status_code != 200:
            logger.error("Amadeus Hotel List by City failed: %d %s", list_res.status_code, list_res.text)
            return json.dumps(get_fallback_hotels(city_iata))

        hotels_data = list_res.json().get("data", [])
        if not hotels_data:
            logger.warning("No hotel IDs found for city code %s. Falling back to mock data.", city_iata)
            return json.dumps(get_fallback_hotels(city_iata))

        # Take up to 3 hotel IDs to avoid hitting limits in Sandbox shopping
        hotel_ids = [h.get("hotelId") for h in hotels_data[:3] if h.get("hotelId")]
        if not hotel_ids:
            return json.dumps(get_fallback_hotels(city_iata))

        # Query v3 shopping/hotel-offers using the retrieved hotelIds
        search_url = "https://test.api.amadeus.com/v3/shopping/hotel-offers"
        search_params = {
            "hotelIds": ",".join(hotel_ids),
            "adults": 1,
            "checkInDate": check_in,
            "checkOutDate": check_out,
            "roomQuantity": 1
        }
        
        search_res = httpx.get(search_url, headers=headers, params=search_params, timeout=5.0)
        if search_res.status_code == 200:
            raw_offers = search_res.json().get("data", [])
            clean_hotels = []
            
            for offer in raw_offers:
                hotel_prop = offer.get("hotel", {})
                name = hotel_prop.get("name", "Local Hotel")
                offers_list = offer.get("offers", [])
                if not offers_list:
                    continue
                first_offer = offers_list[0]
                room_type = first_offer.get("room", {}).get("typeEstimated", {}).get("category", "Standard")
                description = first_offer.get("room", {}).get("description", {}).get("text", "Comfortable room")
                price_info = first_offer.get("price", {})
                price_per_night = price_info.get("total", "N/A")
                currency = price_info.get("currency", "EUR")
                
                clean_hotels.append({
                    "name": name,
                    "price_per_night": f"{currency} {price_per_night}",
                    "currency": currency,
                    "room_type": room_type,
                    "description": description
                })

            if not clean_hotels:
                logger.warning("Amadeus Hotel Offer search returned 0 available offers. Falling back to mock data.")
                clean_hotels = get_fallback_hotels(city_iata)

            result_json = json.dumps(clean_hotels)
            if client:
                try:
                    client.setex(cache_key, 3600, result_json)
                except Exception as exc:
                    logger.warning("Cache write error: %s", exc)

            return result_json
        else:
            logger.error("Amadeus Hotel Shopping API returned status %d: %s", search_res.status_code, search_res.text)
            return json.dumps(get_fallback_hotels(city_iata))

    except Exception as exc:
        logger.exception("Exception occurred during Amadeus Hotel Search: %s", exc)
        return json.dumps(get_fallback_hotels(city_iata))
