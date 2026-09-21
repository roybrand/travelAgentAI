"""Rich, map-ready content for the four showcase destinations (NAP, LIS, TYO, DXB).

Coordinates are approximate, for pin placement only. `cost` is a rough per-person price in
GBP for the activity (0 = free to enjoy). VENUES are FICTIONAL demo listings (restaurants,
tours, experiences) placed near the sights; their prices and discounts are synthetic and the
UI labels them "demo". "Nearby" is genuinely computed from distances.
"""

# code -> (lat, lng) of the city centre, also used to place demo hotels around it
CITY_CENTERS = {
    "NAP": (40.8518, 14.2681),
    "LIS": (38.7223, -9.1393),
    "TYO": (35.6762, 139.6503),
    "DXB": (25.2048, 55.2708),
}


def _i(photo, lat, lng, cost, duration, cost_note=""):
    return {"photo": photo, "lat": lat, "lng": lng, "cost": cost, "duration": duration, "cost_note": cost_note}


# code -> {"hero": photo key, "items": {item name: extras}}; names must match guides_data entries
RICH = {
    "NAP": {
        "hero": "NAP-amalfi",
        "items": {
            "Amalfi Coast (Positano & Amalfi)": _i("NAP-amalfi", 40.6281, 14.4850, 25, "Full day", "return ferry"),
            "Capri": _i("NAP-capri", 40.5532, 14.2222, 35, "Full day", "return ferry"),
            "Pompeii & Herculaneum": _i("NAP-pompeii", 40.7506, 14.4869, 18, "Half day", "entry ticket"),
            "Naples historic centre": _i("NAP-centre", 40.8489, 14.2559, 0, "3-4 hours", "free to wander"),
            "Hike the Path of the Gods": _i("NAP-path", 40.6231, 14.5113, 0, "4-5 hours", "free trail"),
            "Climb Mount Vesuvius": _i("NAP-vesuvius", 40.8214, 14.4260, 12, "3 hours", "crater entry"),
            "Boat day around Capri": _i("NAP-boat", 40.5582, 14.2385, 60, "Full day", "shared boat"),
            "Fine dining around Sorrento": _i("NAP-dining", 40.6263, 14.3758, 120, "Evening", "tasting menu"),
        },
    },
    "LIS": {
        "hero": "LIS-hero",
        "items": {
            "Alfama": _i("LIS-alfama", 38.7110, -9.1290, 0, "3 hours", "free to wander"),
            "Belem": _i("LIS-belem", 38.6916, -9.2160, 8, "Half day", "tower entry"),
            "Sintra": _i("LIS-sintra", 38.7876, -9.3906, 15, "Full day", "palace entry"),
            "Cascais & the coast": _i("LIS-cascais", 38.6979, -9.4215, 5, "Half day", "train fare"),
            "Surf at Guincho or Ericeira": _i("LIS-surf", 38.7297, -9.4738, 45, "3 hours", "group lesson"),
            "Ride Tram 28": _i("LIS-tram", 38.7167, -9.1355, 3, "1 hour", "single fare"),
            "Sunset sail on the Tagus": _i("LIS-sail", 38.7060, -9.1445, 35, "2 hours", "shared sail"),
            "Rooftop bars in Bairro Alto": _i("LIS-bairro", 38.7133, -9.1442, 25, "Evening", "two drinks"),
        },
    },
    "TYO": {
        "hero": "TYO-hero",
        "items": {
            "Shibuya & Shinjuku": _i("TYO-shibuya", 35.6595, 139.7005, 0, "Half day", "free to wander"),
            "Asakusa & Senso-ji": _i("TYO-asakusa", 35.7148, 139.7967, 0, "3 hours", "free to wander"),
            "Meiji Shrine & Harajuku": _i("TYO-meiji", 35.6764, 139.6993, 0, "3 hours", "free entry"),
            "Hakone or Kawaguchiko": _i("TYO-hakone", 35.2324, 139.1069, 45, "Full day", "rail + bus"),
            "Sushi at the Tsukiji outer market": _i("TYO-tsukiji", 35.6655, 139.7707, 35, "2 hours", "breakfast"),
            "Golden Gai bar crawl": _i("TYO-goldengai", 35.6940, 139.7036, 30, "Evening", "a few drinks"),
            "Onsen soak in Hakone": _i("TYO-onsen", 35.2500, 139.0500, 25, "3 hours", "day entry"),
            "Mount Fuji day trip": _i("TYO-fuji", 35.5110, 138.7550, 70, "Full day", "transport"),
        },
    },
    "DXB": {
        "hero": "DXB-hero",
        "items": {
            "Burj Khalifa & Downtown": _i("DXB-burj", 25.1972, 55.2744, 40, "3 hours", "observation deck"),
            "Old Dubai": _i("DXB-old", 25.2637, 55.2972, 1, "3 hours", "abra ride"),
            "Jumeirah & Palm Jumeirah": _i("DXB-palm", 25.1124, 55.1390, 0, "Half day", "public beach"),
            "Abu Dhabi": _i("DXB-abudhabi", 24.4128, 54.4750, 30, "Full day", "transport"),
            "Desert safari": _i("DXB-safari", 24.9500, 55.5500, 55, "6 hours", "shared safari"),
            "Sunrise hot-air balloon": _i("DXB-balloon", 24.9000, 55.4500, 250, "4 hours", "per person"),
            "Supercar drive": _i("DXB-supercar", 25.1930, 55.2790, 200, "90 minutes", "guided drive"),
            "Rooftop dining and lounges": _i("DXB-rooftop", 25.0805, 55.1403, 90, "Evening", "dinner + drinks"),
        },
    },
}

# (name, kind, lat, lng, price per person GBP, rating, blurb). FICTIONAL demo listings.
VENUES = {
    "NAP": [
        ("Trattoria del Faro", "restaurant", 40.6295, 14.4870, 38, 4.6, "Seafood terrace above the beach"),
        ("Positano Boat Tours", "tour", 40.6270, 14.4835, 55, 4.7, "Coastal cruise with a swim stop"),
        ("Capri Grotto Boats", "tour", 40.5590, 14.2390, 32, 4.5, "Blue Grotto boat trip"),
        ("La Terrazza Azzurra", "restaurant", 40.5505, 14.2430, 45, 4.4, "Lemon pasta lunch with a sea view"),
        ("Ristorante Vesuvio Antico", "restaurant", 40.7490, 14.4890, 22, 4.3, "Wood-fired classics near the ruins"),
        ("Pompeii Guided Walk", "tour", 40.7510, 14.4850, 29, 4.6, "Small-group guided ruins tour"),
        ("Pizzeria dei Vicoli", "restaurant", 40.8495, 14.2570, 9, 4.7, "Classic Neapolitan margherita"),
        ("Underground Naples Walk", "tour", 40.8506, 14.2575, 18, 4.5, "Tunnels beneath the old town"),
        ("Agriturismo Sentiero", "restaurant", 40.6240, 14.5100, 28, 4.6, "Farm lunch at the trailhead"),
        ("Vesuvio Wine Tasting", "experience", 40.8150, 14.4300, 35, 4.5, "Volcanic-soil wines with a view"),
        ("Osteria del Golfo", "restaurant", 40.6270, 14.3770, 85, 4.8, "Tasting menu overlooking the bay"),
    ],
    "LIS": [
        ("Tasca do Miradouro", "restaurant", 38.7118, -9.1300, 24, 4.6, "Grilled sardines and vinho verde"),
        ("Fado Night at Casa da Luz", "experience", 38.7105, -9.1275, 40, 4.7, "Live fado with dinner"),
        ("Casa dos Pasteis", "restaurant", 38.6970, -9.2060, 6, 4.5, "Warm custard tarts"),
        ("Quinta das Colinas Cafe", "restaurant", 38.7975, -9.3870, 20, 4.4, "Garden lunch in the hills"),
        ("Sintra Palaces Jeep Tour", "tour", 38.7960, -9.3900, 48, 4.6, "Half-day palace and coast route"),
        ("Marisqueira do Porto", "restaurant", 38.6985, -9.4200, 34, 4.5, "Fresh shellfish by the marina"),
        ("Guincho Surf School", "experience", 38.7300, -9.4750, 45, 4.6, "Group surf lesson, board included"),
        ("Baixa Petiscos", "restaurant", 38.7160, -9.1370, 18, 4.3, "Small plates near the tram stop"),
        ("Tagus Sunset Sail", "tour", 38.7050, -9.1440, 35, 4.7, "Two-hour sunset sailing trip"),
        ("Miradouro Rooftop Bar", "restaurant", 38.7140, -9.1450, 16, 4.4, "Cocktails with city views"),
    ],
    "TYO": [
        ("Izakaya Kemuri", "restaurant", 35.6600, 139.7020, 28, 4.6, "Charcoal skewers and highballs"),
        ("Shibuya Sky Night Pass", "experience", 35.6585, 139.7010, 15, 4.5, "Rooftop views of the crossing"),
        ("Kimono Rental Asakusa", "experience", 35.7140, 139.7955, 32, 4.5, "Traditional dress for temple streets"),
        ("Ebiten Counter", "restaurant", 35.7155, 139.7980, 26, 4.6, "Counter-seat tempura"),
        ("Harajuku Crepe House", "restaurant", 35.6700, 139.7030, 7, 4.2, "Street crepes near the shrine"),
        ("Yumoto Soba House", "restaurant", 35.2330, 139.1080, 14, 4.5, "Buckwheat noodles by the river"),
        ("Sushi Counter Umi", "restaurant", 35.6650, 139.7715, 55, 4.8, "Omakase-style sushi breakfast"),
        ("Market Food Walk", "tour", 35.6660, 139.7695, 42, 4.6, "Guided tasting through the market"),
        ("Bar Hoshi Lane", "restaurant", 35.6945, 139.7040, 22, 4.5, "Tiny themed bar, two drinks included"),
        ("Gora Onsen Retreat", "spa", 35.2505, 139.0510, 38, 4.7, "Day-use outdoor onsen"),
        ("Kawaguchiko Lake Cruise", "tour", 35.5120, 138.7560, 20, 4.4, "Lake cruise with Fuji views"),
    ],
    "DXB": [
        ("Downtown Fountain Brunch", "restaurant", 25.1960, 55.2760, 48, 4.4, "Brunch with fountain views"),
        ("Creekside Shawarma House", "restaurant", 25.2640, 55.2960, 7, 4.5, "Local favourites by the water"),
        ("Souk Spice Walk", "tour", 25.2650, 55.2985, 18, 4.4, "Guided souk tasting walk"),
        ("Palm Beach Club Day Pass", "experience", 25.1130, 55.1380, 45, 4.3, "Pool and beach access"),
        ("Grand Mosque Guided Tour", "tour", 24.4130, 54.4760, 20, 4.7, "Guided tour with cultural briefing"),
        ("Bedouin Camp Dinner", "experience", 24.9510, 55.5490, 60, 4.6, "BBQ dinner and shows at camp"),
        ("Dawn Balloon Breakfast", "experience", 24.9010, 55.4510, 270, 4.7, "Sunrise flight with breakfast"),
        ("Downtown Supercar Hire", "experience", 25.1935, 55.2800, 210, 4.5, "90-minute exotic drive"),
        ("Marina Skyline Lounge", "restaurant", 25.0810, 55.1410, 75, 4.5, "Cocktails and skyline views"),
    ],
}
