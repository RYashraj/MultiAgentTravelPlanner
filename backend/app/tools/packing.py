def generate_packing_list(weather_condition: str, duration_days: int, destination_type: str) -> list[str]:
    """
    Generate a rule-based packing list based on:
    - weather_condition (e.g. Sunny, Rainy, Cold, Pleasant)
    - duration_days (length of the trip)
    - destination_type (beach, adventure, city)
    """
    # 1. Base items (essential for all trips)
    items = [
        "Passport / ID, visa & travel documents",
        "Phone charger & power bank",
        "Universal travel adapter",
        "Toiletries (toothbrush, toothpaste, deodorant, shampoo)",
        f"Underwear (x{duration_days})",
        f"Socks (x{duration_days})",
        "Sleepwear / pajamas",
        "Personal medications & first-aid kit",
        "Refillable water bottle",
    ]

    # 2. Weather-based items
    weather = (weather_condition or "").lower()
    if any(kw in weather for kw in ("rain", "drizzle", "storm", "shower", "thunderstorm", "wet")):
        items.extend([
            "Compact umbrella",
            "Waterproof jacket or raincoat",
            "Waterproof shoes or boots",
            "Ziploc bags for wet items",
        ])
    elif any(kw in weather for kw in ("snow", "cold", "freeze", "winter", "chilly", "ice", "frost")):
        items.extend([
            "Heavy winter coat / thermal jacket",
            "Thermal base layers (tops & bottoms)",
            "Gloves & thick wool scarf",
            "Beanie / warm hat",
            "Lip balm & heavy moisturizer",
        ])
    elif any(kw in weather for kw in ("sun", "hot", "summer", "warm", "clear", "heat")):
        items.extend([
            "Polarized sunglasses",
            "Sunscreen (SPF 50+)",
            "Wide-brimmed sun hat or cap",
            "Lightweight & breathable t-shirts / linen clothes",
            "After-sun cooling gel (Aloe vera)",
        ])
    else:
        # Pleasant / Mild / Cloudy / default temperate weather
        items.extend([
            "Light jacket, sweater, or cardigan",
            "Comfortable sneakers / walking shoes",
            "Versatile layering t-shirts",
        ])

    # 3. Destination type-based items (beach, adventure, city)
    dest = (destination_type or "").lower()
    if dest == "beach":
        items.extend([
            "Swimwear (swim trunks / bikini)",
            "Quick-dry microfiber beach towel",
            "Flip-flops or water shoes",
            "Waterproof phone pouch",
            "Beach bag or tote",
        ])
    elif dest == "adventure":
        items.extend([
            "Sturdy hiking boots / trail runners",
            "Insect repellent (DEET or Picaridin)",
            "Mini pocket flashlight or headlamp",
            "Comfortable daypack / backpack",
            "Quick-dry hiking trousers",
        ])
    else:
        # Default/City
        items.extend([
            "Smart casual outfits for dining out",
            "Comfortable urban walking shoes",
            "Crossbody bag or anti-theft daypack",
            "Hand sanitizer & wet wipes",
        ])

    return items
