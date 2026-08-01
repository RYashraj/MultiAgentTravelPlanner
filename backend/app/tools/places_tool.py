import json

from langchain_core.tools import tool

# ─────────────────────────────────────────────────────────────────
# Comprehensive mock data — budget-aware, real place names, pricing
# ─────────────────────────────────────────────────────────────────
MOCK_PLACES_DB = {
    "Mumbai": [
        # Attractions
        {"name": "Gateway of India", "type": "attraction", "rating": 4.6, "description": "Iconic colonial-era arch monument on the waterfront — free entry, best visited at sunrise or sunset."},
        {"name": "Marine Drive (Queen's Necklace)", "type": "attraction", "rating": 4.8, "description": "3.6-km seafront promenade — perfect for a morning walk or evening hangout. Free entry."},
        {"name": "Elephanta Caves", "type": "attraction", "rating": 4.4, "description": "UNESCO World Heritage rock-cut cave temples on Elephanta Island. Ferry from Gateway: ₹200 return, cave entry ₹40."},
        {"name": "Chhatrapati Shivaji Maharaj Terminus (CST)", "type": "attraction", "rating": 4.5, "description": "UNESCO-listed Victorian Gothic railway station — a stunning free architectural landmark."},
        {"name": "Dharavi Slum Tour", "type": "attraction", "rating": 4.3, "description": "Eye-opening guided tour of Asia's largest slum and informal economy hub. Tour: ₹800–₹1,200."},
        {"name": "Haji Ali Dargah", "type": "attraction", "rating": 4.6, "description": "Beautiful islet mosque accessible at low tide via a narrow causeway. Free entry, open to all."},
        {"name": "Juhu Beach", "type": "attraction", "rating": 4.1, "description": "Popular beach known for street food stalls (pav bhaji, bhel puri). Great for a free evening out."},
        {"name": "Sanjay Gandhi National Park", "type": "attraction", "rating": 4.3, "description": "Urban forest with leopards, Kanheri Caves, and nature trails. Entry ₹50–₹100."},

        # Shopping — the KEY fix
        {"name": "Fashion Street (MG Road)", "type": "shopping", "rating": 4.4, "description": "Mumbai's most famous budget street market — jeans ₹200–₹600, T-shirts ₹100–₹300, ethnic wear ₹300–₹800. Bargaining is a must!"},
        {"name": "Linking Road, Bandra", "type": "shopping", "rating": 4.5, "description": "Trendy street shopping hub in Bandra — streetwear, sneakers, western wear. Prices ₹200–₹1,500. Very popular with youth."},
        {"name": "Colaba Causeway Market", "type": "shopping", "rating": 4.3, "description": "Iconic street bazaar selling antiques, jewellery, bags, clothes. Great for souvenirs and unique finds. Prices ₹100–₹2,000."},
        {"name": "Hill Road, Bandra", "type": "shopping", "rating": 4.2, "description": "Great for budget western wear, accessories and streetwear brands. Prices ₹200–₹1,000."},
        {"name": "Phoenix Palladium Mall", "type": "shopping", "rating": 4.5, "description": "Premium mall with Zara, H&M, Mango, Adidas. Lower Parel. Good food court. Mix of mid-range to luxury brands."},
        {"name": "Infiniti Mall (Andheri / Malad)", "type": "shopping", "rating": 4.2, "description": "Large mall with Decathlon, Westside, Hamleys, multiplex cinema. Budget-friendly anchor stores. Great for a full shopping day."},
        {"name": "Crawford Market (Mahatma Jyotiba Phule Market)", "type": "shopping", "rating": 4.1, "description": "Historic wholesale market — dry fruits, spices, fruits, cheap homeware and more. Very affordable prices."},
        {"name": "Dharavi Leather Market", "type": "shopping", "rating": 4.0, "description": "Genuine leather goods — bags, wallets, belts at factory prices. Bags ₹500–₹2,000. Best budget leather in Mumbai."},

        # Restaurants
        {"name": "Bademiyan (Colaba)", "type": "restaurant", "rating": 4.3, "description": "Legendary street-side kebab stall open since 1946. Must-try seekh kebabs and rolls. Meal ₹100–₹300 per person."},
        {"name": "Sardar Pav Bhaji (Tardeo)", "type": "restaurant", "rating": 4.5, "description": "Mumbai's most famous pav bhaji joint — serving since 1945. Iconic dish for ₹80–₹150 per plate. Cash only."},
        {"name": "Café Madras (Matunga)", "type": "restaurant", "rating": 4.4, "description": "Legendary South Indian restaurant. Masala dosa, idli-vada. Full breakfast under ₹200. Pure vegetarian."},
        {"name": "Trishna Restaurant (Fort)", "type": "restaurant", "rating": 4.6, "description": "Iconic seafood restaurant. Try the butter-garlic crab! Meal ₹800–₹1,500 per person."},
        {"name": "Leopold Cafe (Colaba)", "type": "restaurant", "rating": 4.2, "description": "Historic restaurant and bar on Colaba Causeway since 1871. Good for Western food. Meal ₹400–₹800."},
        {"name": "Elco Pani Puri & Chaat Centre (Bandra)", "type": "restaurant", "rating": 4.4, "description": "Best chaat, pani puri, and bhel puri in Mumbai. Snacks ₹50–₹150. Always packed with locals."},
        {"name": "Swati Snacks (Tardeo)", "type": "restaurant", "rating": 4.6, "description": "Famous for Gujarati snacks and thalis — perfect for travellers from Gujarat! Meal ₹200–₹400."},

        # Budget Hotels
        {"name": "Hotel Suba Palace (Budget)", "type": "hotel", "budget_type": "budget", "rating": 3.9, "description": "Clean budget hotel near CST. Rooms ₹1,200–₹2,500/night. Good for backpackers and solo travellers. WiFi included."},
        {"name": "Zostel Mumbai (Colaba)", "type": "hotel", "budget_type": "budget", "rating": 4.1, "description": "Popular backpacker hostel in Colaba. Dorm beds ₹600–₹900/night, private rooms ₹1,800–₹2,500/night. Great social atmosphere."},
        {"name": "Hotel City Palace (Near CST)", "type": "hotel", "budget_type": "budget", "rating": 3.8, "description": "Budget hotel near CST station. Rooms ₹1,500–₹2,200/night. Clean and well-located for exploring South Mumbai."},
        {"name": "Hotel Bentley's (Colaba)", "type": "hotel", "budget_type": "budget", "rating": 3.7, "description": "Affordable colonial-era guesthouse. Rooms ₹1,800–₹3,000/night. Basic amenities, great Colaba location."},

        # Mid-range Hotels
        {"name": "Ibis Mumbai Vikhroli (Mid-Range)", "type": "hotel", "budget_type": "midrange", "rating": 4.2, "description": "Modern business hotel. Rooms ₹3,500–₹5,500/night. Excellent reviews, clean, good breakfast included."},
        {"name": "Hotel Fariyas (Colaba)", "type": "hotel", "budget_type": "midrange", "rating": 4.0, "description": "Well-located mid-range hotel in South Mumbai. Rooms ₹4,000–₹7,000/night. Pool, restaurant, great staff."},

        # Luxury Hotels (shown only when budget permits)
        {"name": "The Taj Mahal Palace (Luxury)", "type": "hotel", "budget_type": "luxury", "rating": 4.9, "description": "Iconic 5-star heritage hotel. Rooms ₹20,000–₹80,000/night. Only if budget is luxury/no limit."},
    ],

    "Delhi": [
        {"name": "Red Fort", "type": "attraction", "rating": 4.5, "description": "UNESCO World Heritage Mughal fort. Entry ₹50 (Indian nationals). Sound & Light show in evenings."},
        {"name": "Qutub Minar", "type": "attraction", "rating": 4.6, "description": "UNESCO-listed 12th century minaret. Entry ₹40 (Indian nationals). Best in morning light."},
        {"name": "India Gate", "type": "attraction", "rating": 4.5, "description": "War memorial and iconic Delhi landmark. Free entry. Great evening picnic spot."},
        {"name": "Humayun's Tomb", "type": "attraction", "rating": 4.6, "description": "Mughal garden tomb, predecessor to the Taj Mahal. Entry ₹40."},
        {"name": "Lodi Garden", "type": "attraction", "rating": 4.5, "description": "Beautiful garden with 15th century tombs. Free entry. Morning yoga and walking popular."},

        {"name": "Sarojini Nagar Market", "type": "shopping", "rating": 4.5, "description": "Delhi's most popular budget fashion market. Export surplus garments ₹50–₹500. Jeans, tops, kurtas. Go in the morning before it gets crowded."},
        {"name": "Janpath Market (Connaught Place)", "type": "shopping", "rating": 4.3, "description": "Street market near CP — ethnic wear, jewellery, bags, handicrafts. Prices ₹100–₹800. Popular with tourists."},
        {"name": "Lajpat Nagar Central Market", "type": "shopping", "rating": 4.3, "description": "South Delhi's best market — mix of clothes, home decor, wedding shopping. Budget to mid-range."},
        {"name": "Select Citywalk Mall (Saket)", "type": "shopping", "rating": 4.4, "description": "Premium mall with Zara, Mango, H&M, Uniqlo. Great food court and multiplex."},
        {"name": "Chandni Chowk", "type": "shopping", "rating": 4.2, "description": "Historic bazaar near Red Fort — spices, silver jewellery, saris, street food. Very affordable wholesale prices."},

        {"name": "Paranthe Wali Gali (Chandni Chowk)", "type": "restaurant", "rating": 4.4, "description": "Famous narrow lane of stuffed paratha shops. 100+ years old. Meal ₹60–₹150 per paratha."},
        {"name": "Moti Mahal (Daryaganj)", "type": "restaurant", "rating": 4.3, "description": "Birthplace of butter chicken! Must-visit Delhi legend. Meal ₹400–₹800."},
        {"name": "Karim's (Jama Masjid)", "type": "restaurant", "rating": 4.5, "description": "Iconic Mughal cuisine restaurant since 1913. Try mutton korma and naan. Meal ₹300–₹700."},

        {"name": "Zostel Delhi (Paharganj)", "type": "hotel", "budget_type": "budget", "rating": 4.2, "description": "Popular backpacker hostel. Dorm ₹500–₹800/night. Private rooms ₹1,500–₹2,500/night. Near New Delhi station."},
        {"name": "Hotel Ajanta (Paharganj)", "type": "hotel", "budget_type": "budget", "rating": 3.8, "description": "Budget hotel near New Delhi station. Rooms ₹1,200–₹2,000/night. Clean and practical."},
        {"name": "Bloom Rooms (Janakpuri)", "type": "hotel", "budget_type": "midrange", "rating": 4.3, "description": "Modern mid-range hotel. Rooms ₹3,000–₹5,000/night. Good reviews, AC, breakfast available."},
    ],

    "Goa": [
        {"name": "Baga Beach", "type": "attraction", "rating": 4.2, "description": "North Goa's liveliest beach — water sports (parasailing ₹500, jet ski ₹800), shacks, nightlife."},
        {"name": "Basilica of Bom Jesus", "type": "attraction", "rating": 4.6, "description": "UNESCO World Heritage site. Free entry. Contains the tomb of St. Francis Xavier."},
        {"name": "Dudhsagar Waterfalls", "type": "attraction", "rating": 4.7, "description": "Spectacular 4-tiered waterfall. Jeep safari from Molem ₹1,500–₹2,000 per jeep. Best in monsoon."},
        {"name": "Anjuna Flea Market", "type": "shopping", "rating": 4.1, "description": "Famous Wednesday flea market — clothes, jewellery, handicrafts, bongs. Very touristy but fun. Prices ₹100–₹2,000."},
        {"name": "Mapusa Friday Market", "type": "shopping", "rating": 4.2, "description": "Authentic local Goan market on Fridays. Spices, pickles, clothing, fresh produce. Best for local souvenirs."},
        {"name": "Britto's (Baga)", "type": "restaurant", "rating": 4.1, "description": "Iconic beach shack. Fresh seafood — fish thali ₹250–₹400, prawn curry ₹350–₹600. Great atmosphere."},
        {"name": "Fisherman's Wharf (South Goa)", "type": "restaurant", "rating": 4.4, "description": "Waterfront restaurant. Best prawn balchão and Goan fish curry. Meal ₹500–₹900."},
        {"name": "Zostel Goa (Vagator)", "type": "hotel", "budget_type": "budget", "rating": 4.3, "description": "Top-rated hostel. Dorm beds ₹700–₹1,000/night. Pool, rooftop bar, great social vibe."},
        {"name": "Taj Exotica Resort (Luxury)", "type": "hotel", "budget_type": "luxury", "rating": 4.8, "description": "Mediterranean-style 5-star resort on Benaulim beach. Rooms ₹18,000–₹50,000/night."},
    ],

    "Tokyo": [
        {"name": "Senso-ji Temple", "type": "attraction", "rating": 4.7, "description": "Tokyo's oldest Buddhist temple in Asakusa. Free entry. Best at dawn before crowds arrive."},
        {"name": "Shibuya Crossing", "type": "attraction", "rating": 4.6, "description": "World's busiest pedestrian crossing. Free. Best viewed from Starbucks or Mag's Park above."},
        {"name": "Akihabara Electric Town", "type": "shopping", "rating": 4.5, "description": "Electronics, anime, manga, gaming merchandise. Great for tech deals and unique Japanese pop culture items."},
        {"name": "Harajuku (Takeshita Street)", "type": "shopping", "rating": 4.4, "description": "Tokyo's famous youth fashion street — quirky streetwear, pop culture items, crepes. Very Instagrammable."},
        {"name": "Ichiran Ramen", "type": "restaurant", "rating": 4.5, "description": "Famous tonkotsu ramen chain with private solo dining booths. Ramen ¥900–¥1,500."},
        {"name": "Tsukiji Outer Market", "type": "restaurant", "rating": 4.5, "description": "Fresh sushi, sashimi, tamagoyaki from market stalls. Early morning breakfast under ¥2,000. Unmissable."},
        {"name": "Khaosan Tokyo Hostel (Budget)", "type": "hotel", "budget_type": "budget", "rating": 4.1, "description": "Budget hostel in Asakusa. Dorm ¥2,500–₹3,500/night. Great location near Senso-ji."},
        {"name": "Park Hyatt Tokyo (Luxury)", "type": "hotel", "budget_type": "luxury", "rating": 4.8, "description": "Luxury hotel from 'Lost in Translation'. Rooms ¥65,000+/night."},
    ],
}

# ─────────────────────────────────────────────────────────────────
# Transport data — trains + flights with real prices
# ─────────────────────────────────────────────────────────────────
TRANSPORT_DB = {
    ("Gujarat", "Mumbai"): {
        "train": "Gujarat→Mumbai: Multiple daily trains from Ahmedabad/Surat/Vadodara. Shatabdi Express (Ahmedabad→Mumbai): ~7 hrs, ₹700–₹1,500 (CC/EC class). Rajdhani Express: ~8 hrs, ₹1,200–₹2,000. Book on IRCTC.co.in.",
        "flight": "Flights from Ahmedabad (AMD) to Mumbai (BOM): 1 hr, ₹1,500–₹4,000 (IndiGo/Air India). Book 2–3 weeks ahead for best fares on MakeMyTrip.",
        "bus": "GSRTC/private overnight buses: 8–10 hrs, ₹300–₹800. Book on redBus.in.",
    },
    ("Delhi", "Mumbai"): {
        "train": "Delhi→Mumbai: Rajdhani Express: ~16 hrs, ₹1,500–₹3,000. Mumbai Duronto: ~18 hrs, ₹1,200–₹2,500. Book IRCTC.",
        "flight": "Delhi (DEL) to Mumbai (BOM): 2 hrs, ₹2,500–₹6,000. Frequent flights all day.",
        "bus": "Overnight Volvo buses: ~22 hrs, ₹800–₹1,500.",
    },
}

def get_transport_info(origin: str, destination: str) -> str:
    """Get transport options between origin and destination."""
    if not origin:
        return ""

    origin_lower = origin.lower()
    dest_lower = destination.lower()

    # Try to match transport routes
    for (orig_key, dest_key), data in TRANSPORT_DB.items():
        if orig_key.lower() in origin_lower and dest_key.lower() in dest_lower:
            return (
                f"## 🚆 Getting to {destination}\n\n"
                f"**🚂 Train**: {data['train']}\n\n"
                f"**✈️ Flight**: {data['flight']}\n\n"
                f"**🚌 Bus**: {data['bus']}\n"
            )

    # Generic fallback
    return (
        f"## 🚆 Getting to {destination}\n\n"
        f"**✈️ Flight**: Check Google Flights or MakeMyTrip for {origin} → {destination} routes. "
        f"Book 2–4 weeks ahead for best prices.\n\n"
        f"**🚂 Train**: Check IRCTC.co.in for train options. Rajdhani/Shatabdi Express recommended for comfort.\n\n"
        f"**🚌 Bus**: Check redBus.in for overnight Volvo buses — affordable option.\n"
    )


def get_budget_hotels(places: list, budget: str | None = None) -> list:
    """Filter hotels based on budget keyword."""
    if not places:
        return []

    budget_lower = (budget or "").lower()

    # Determine budget tier
    if any(w in budget_lower for w in ["luxury", "no limit", "unlimited", "5 star", "premium"]):
        tier = "luxury"
    elif any(w in budget_lower for w in ["budget", "cheap", "low", "backpack", "hostel", "₹1", "₹2", "1000", "2000"]):
        tier = "budget"
    else:
        tier = "midrange"

    hotels = [p for p in places if p.get("type") == "hotel"]

    # Filter by budget tier
    budget_hotels = [h for h in hotels if h.get("budget_type") == tier]
    if budget_hotels:
        return budget_hotels

    # Fallback: midrange if exact tier not found
    midrange = [h for h in hotels if h.get("budget_type") == "midrange"]
    if midrange:
        return midrange

    # Last resort: return first hotel (but exclude luxury if budget-friendly)
    if tier == "budget":
        return [h for h in hotels if h.get("budget_type") != "luxury"][:2]

    return hotels[:2]


@tool
def search_places(location: str, query_type: str) -> str:
    """
    Search for places, attractions, restaurants, shopping areas or hotels in a given location.

    Args:
        location: The city or region (e.g., "Mumbai", "Tokyo").
        query_type: The type of place to search for (e.g., "attraction", "restaurant", "hotel", "shopping", "all").

    Returns:
        A JSON string containing a list of places matching the criteria.
    """
    loc_key = next((k for k in MOCK_PLACES_DB if k.lower() in location.lower() or location.lower() in k.lower()), None)

    if not loc_key:
        return json.dumps([
            {"name": f"Old Town of {location}", "type": "attraction", "rating": 4.5, "description": f"Historic city centre of {location} with local culture and architecture."},
            {"name": f"Local Market in {location}", "type": "shopping", "rating": 4.3, "description": f"Main shopping bazaar in {location} — local clothes, crafts, street food. Budget-friendly."},
            {"name": f"Budget Inn {location}", "type": "hotel", "budget_type": "budget", "rating": 3.9, "description": f"Clean budget hotel in central {location}. Rooms approx ₹1,500–₹2,500/night."},
            {"name": f"Mid-Range Hotel {location}", "type": "hotel", "budget_type": "midrange", "rating": 4.2, "description": f"Comfortable hotel in {location}. Rooms ₹3,000–₹6,000/night."},
            {"name": "Local Cuisine Restaurant", "type": "restaurant", "rating": 4.4, "description": f"Best local food in {location}. Try the regional specialities. Meal ₹200–₹500."},
        ])

    places = MOCK_PLACES_DB[loc_key]

    if query_type.lower() != "all":
        filtered = [p for p in places if p["type"] == query_type.lower()]
        return json.dumps(filtered if filtered else places)

    return json.dumps(places)
