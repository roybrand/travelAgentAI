"""Curated destination knowledge for the prototype guides MCP server.

This is hand-written, general travel knowledge (climate seasons, well-known sights),
not live data. It stands in for what a RAG layer over travel guides would supply
later. `months` is a 1-5 suitability score for Jan..Dec, weighing weather, crowds
and typical peak-season pressure.

Item tags reuse the interest vocabulary the hotel search understands, so the UI can
highlight the places and adventures that match what the traveler said they like.
"""

import calendar
import math
import zlib
from datetime import date, timedelta

try:  # imported as app.mcp_tools.guides_data (tests) ...
    from .guides_rich import CITY_CENTERS, RICH, VENUES
except ImportError:  # ... or as a top-level module when guides_server.py runs as a script
    from guides_rich import CITY_CENTERS, RICH, VENUES

GUIDES = {
    "NAP": {
        "name": "Naples & the Amalfi Coast, Italy",
        "months": [2, 2, 3, 4, 5, 5, 4, 3, 5, 4, 2, 2],
        "season_note": "May-June and September-October are warm with swimmable seas and thinner crowds. "
                       "July-August is hot and packed on the coast; winter is mild but many coastal venues close.",
        "places": [
            {"name": "Amalfi Coast (Positano & Amalfi)", "why": "Cliffside villages and some of Italy's best coastal views", "tags": ["beachfront"]},
            {"name": "Capri", "why": "Island day trip with the Blue Grotto and clifftop walks", "tags": ["beachfront"]},
            {"name": "Pompeii & Herculaneum", "why": "The best-preserved Roman towns in the world", "tags": []},
            {"name": "Naples historic centre", "why": "Spaccanapoli, street life and the birthplace of pizza", "tags": ["old-town", "nightlife"]},
        ],
        "adventures": [
            {"name": "Hike the Path of the Gods", "why": "High trail above the Amalfi Coast", "tags": []},
            {"name": "Climb Mount Vesuvius", "why": "Walk to the crater rim above the bay", "tags": []},
            {"name": "Boat day around Capri", "why": "Swim stops and sea caves", "tags": ["beachfront"]},
            {"name": "Fine dining around Sorrento", "why": "Michelin-recognised restaurants with sea views", "tags": ["michelin-nearby"]},
        ],
        "tips": ["Ferries beat the coastal road in summer traffic.", "Book Pompeii tickets ahead in high season."],
    },
    "LIS": {
        "name": "Lisbon & Sintra, Portugal",
        "months": [2, 2, 3, 4, 5, 5, 4, 3, 5, 5, 3, 2],
        "season_note": "Late spring and early autumn are sunny and comfortable. July-August is hot and busy; "
                       "winter is mild but wet.",
        "places": [
            {"name": "Alfama", "why": "Lisbon's oldest quarter: tiled lanes, viewpoints and fado", "tags": ["old-town", "nightlife"]},
            {"name": "Belem", "why": "Jeronimos Monastery, Belem Tower and the famous custard tarts", "tags": []},
            {"name": "Sintra", "why": "Fairy-tale palaces in the hills, an easy day trip", "tags": []},
            {"name": "Cascais & the coast", "why": "Beaches and seaside promenade west of the city", "tags": ["beachfront"]},
        ],
        "adventures": [
            {"name": "Surf at Guincho or Ericeira", "why": "Reliable Atlantic waves close to the city", "tags": ["beachfront"]},
            {"name": "Ride Tram 28", "why": "A classic route through the old neighbourhoods", "tags": ["old-town"]},
            {"name": "Sunset sail on the Tagus", "why": "See the city skyline from the river", "tags": []},
            {"name": "Rooftop bars in Bairro Alto", "why": "Lively evenings with city views", "tags": ["nightlife", "rooftop-bar"]},
        ],
        "tips": ["Wear grippy shoes: the cobbled hills are slippery.", "Go to Sintra early to beat the crowds."],
    },
    "TYO": {
        "name": "Tokyo & around, Japan",
        "months": [3, 3, 5, 5, 4, 2, 2, 2, 3, 5, 5, 3],
        "season_note": "Late March-April (cherry blossom) and October-November (autumn colour) are the sweet spots. "
                       "June is the rainy season, July-August is hot and humid, and September can bring typhoons.",
        "places": [
            {"name": "Shibuya & Shinjuku", "why": "Neon crossings, towers and endless dining", "tags": ["nightlife"]},
            {"name": "Asakusa & Senso-ji", "why": "Tokyo's oldest temple and traditional streets", "tags": ["old-town"]},
            {"name": "Meiji Shrine & Harajuku", "why": "A forest shrine next to youth fashion streets", "tags": []},
            {"name": "Hakone or Kawaguchiko", "why": "Day trip for Mount Fuji views and hot springs", "tags": ["spa"]},
        ],
        "adventures": [
            {"name": "Sushi at the Tsukiji outer market", "why": "Breakfast-grade sushi and street food", "tags": ["michelin-nearby"]},
            {"name": "Golden Gai bar crawl", "why": "Tiny themed bars in Shinjuku", "tags": ["nightlife"]},
            {"name": "Onsen soak in Hakone", "why": "Traditional hot spring with mountain views", "tags": ["spa", "quiet"]},
            {"name": "Mount Fuji day trip", "why": "Lakes and viewpoints around Japan's icon", "tags": []},
        ],
        "tips": ["Get a rechargeable transit card on arrival.", "Book popular restaurants well in advance."],
    },
    "DXB": {
        "name": "Dubai & Abu Dhabi, UAE",
        "months": [5, 5, 5, 3, 2, 1, 1, 1, 2, 4, 5, 5],
        "season_note": "November-March is warm and dry, ideal for beaches and the desert. "
                       "June-September is extremely hot (40C+), so most activity moves indoors.",
        "places": [
            {"name": "Burj Khalifa & Downtown", "why": "The world's tallest tower, fountain show and Dubai Mall", "tags": []},
            {"name": "Old Dubai", "why": "Souks, Al Fahidi district and abra boat rides across the creek", "tags": ["old-town"]},
            {"name": "Jumeirah & Palm Jumeirah", "why": "Beaches and resort waterfront", "tags": ["beachfront", "spa"]},
            {"name": "Abu Dhabi", "why": "Sheikh Zayed Mosque and Ferrari World, an easy day trip", "tags": ["supercar-rental-nearby"]},
        ],
        "adventures": [
            {"name": "Desert safari", "why": "Dune driving and a sunset camp dinner", "tags": []},
            {"name": "Sunrise hot-air balloon", "why": "Float over the dunes at dawn", "tags": ["quiet"]},
            {"name": "Supercar drive", "why": "Rent an exotic car for a coastal run", "tags": ["supercar-rental-nearby"]},
            {"name": "Rooftop dining and lounges", "why": "Skyline views from Downtown and the Marina", "tags": ["nightlife", "rooftop-bar", "michelin-nearby"]},
        ],
        "tips": ["Dress modestly at mosques and traditional areas.", "Plan outdoor activities for early morning or evening."],
    },
    "BCN": {
        "name": "Barcelona, Spain",
        "months": [2, 2, 3, 4, 5, 5, 4, 3, 5, 4, 3, 2],
        "season_note": "May-June and September-October are warm with beach weather and manageable crowds. "
                       "July-August is hot and the busiest time of year.",
        "places": [
            {"name": "Sagrada Familia", "why": "Gaudi's unfinished basilica, the city's icon", "tags": []},
            {"name": "Park Guell & Gracia", "why": "Mosaic terraces and a village-like neighbourhood", "tags": []},
            {"name": "Gothic Quarter & El Born", "why": "Medieval lanes, tapas bars and nightlife", "tags": ["old-town", "nightlife"]},
            {"name": "Barceloneta", "why": "The city beach and seafront promenade", "tags": ["beachfront"]},
        ],
        "adventures": [
            {"name": "Hike Montserrat", "why": "Jagged mountain and monastery an hour from the city", "tags": []},
            {"name": "Tapas crawl in El Born", "why": "Small plates and local wine", "tags": ["nightlife"]},
            {"name": "Sunset sail", "why": "The skyline and coast from the water", "tags": ["beachfront"]},
            {"name": "Costa Brava day trip", "why": "Coves and fishing villages north of the city", "tags": ["beachfront", "quiet"]},
        ],
        "tips": ["Book Sagrada Familia timed entry early.", "Watch for pickpockets around the Ramblas."],
    },
    "ROM": {
        "name": "Rome, Italy",
        "months": [2, 3, 3, 5, 5, 4, 3, 2, 5, 5, 3, 3],
        "season_note": "April-May and September-October are pleasant and less crowded. "
                       "July-August is hot and many locals leave; winter is quiet and mild.",
        "places": [
            {"name": "Colosseum & Roman Forum", "why": "The heart of ancient Rome", "tags": ["old-town"]},
            {"name": "Vatican Museums & St Peter's", "why": "Sistine Chapel and the world's largest church", "tags": []},
            {"name": "Trevi Fountain & Pantheon", "why": "Walkable landmarks in the historic centre", "tags": ["old-town"]},
            {"name": "Trastevere", "why": "Cobbled lanes, trattorias and lively evenings", "tags": ["nightlife", "michelin-nearby"]},
        ],
        "adventures": [
            {"name": "Vespa tour", "why": "See the city's hills and viewpoints on two wheels", "tags": ["supercar-rental-nearby"]},
            {"name": "Cycle the Appian Way", "why": "Ancient road and catacombs outside the centre", "tags": ["quiet"]},
            {"name": "Pasta-making class", "why": "Learn Roman classics from a local cook", "tags": []},
            {"name": "Day trip to Tivoli", "why": "Renaissance and Roman villa gardens", "tags": ["quiet"]},
        ],
        "tips": ["Book Vatican and Colosseum slots in advance.", "Carry a refillable bottle: street fountains are free."],
    },
    "PAR": {
        "name": "Paris, France",
        "months": [2, 2, 3, 4, 5, 5, 4, 3, 5, 4, 2, 3],
        "season_note": "Late spring and early autumn are the best balance of weather and crowds. "
                       "July-August is busy, and winter is grey but atmospheric, with festive lights in December.",
        "places": [
            {"name": "Louvre & Tuileries", "why": "The world's largest art museum and its gardens", "tags": []},
            {"name": "Eiffel Tower & Champ de Mars", "why": "The classic view, best at sunset", "tags": []},
            {"name": "Montmartre", "why": "Hilltop village feel, Sacre-Coeur and cabarets", "tags": ["old-town", "nightlife"]},
            {"name": "Le Marais & Ile Saint-Louis", "why": "Historic streets, boutiques and cafes", "tags": ["old-town"]},
        ],
        "adventures": [
            {"name": "Day trip to Versailles", "why": "The palace and gardens by train", "tags": []},
            {"name": "Seine evening cruise", "why": "Landmarks lit up from the river", "tags": ["quiet"]},
            {"name": "Pastry and bakery crawl", "why": "Croissants, eclairs and macarons by neighbourhood", "tags": ["michelin-nearby"]},
            {"name": "Rooftop drinks", "why": "Skyline views over the city", "tags": ["nightlife", "rooftop-bar"]},
        ],
        "tips": ["A museum pass saves queueing time.", "Book top restaurants weeks ahead."],
    },
    "ATH": {
        "name": "Athens & the islands, Greece",
        "months": [2, 2, 3, 5, 5, 4, 3, 3, 5, 5, 3, 2],
        "season_note": "April-May and September-October are warm and comfortable. "
                       "July-August can bring heatwaves and peak crowds, so sightseeing is best early or late in the day.",
        "places": [
            {"name": "Acropolis & Parthenon", "why": "The defining ancient site of Athens", "tags": ["old-town"]},
            {"name": "Plaka & Monastiraki", "why": "Old-town lanes, markets and tavernas", "tags": ["old-town", "nightlife"]},
            {"name": "Cape Sounion", "why": "Temple of Poseidon above the sea, best at sunset", "tags": ["beachfront"]},
            {"name": "Aegina or Hydra", "why": "Easy island day trips by ferry", "tags": ["beachfront", "quiet"]},
        ],
        "adventures": [
            {"name": "Sunset at Sounion", "why": "Drive the coast road to the temple", "tags": ["beachfront"]},
            {"name": "Island day trip", "why": "Swim and eat by the harbour", "tags": ["beachfront"]},
            {"name": "Hike Mount Lycabettus", "why": "Panoramic views over the city", "tags": []},
            {"name": "Rooftop dinner facing the Acropolis", "why": "Greek dining with an unbeatable view", "tags": ["rooftop-bar", "nightlife", "michelin-nearby"]},
        ],
        "tips": ["Visit the Acropolis at opening time or late afternoon.", "Book island ferries ahead in summer."],
    },
    "NYC": {
        "name": "New York City, USA",
        "months": [2, 2, 3, 4, 5, 5, 3, 3, 5, 5, 4, 4],
        "season_note": "May-June and September-October are mild and lively. July-August is hot and humid. "
                       "December is festive but cold and among the priciest times.",
        "places": [
            {"name": "Central Park", "why": "Green heart of Manhattan, lovely in any season", "tags": ["quiet"]},
            {"name": "Statue of Liberty & Ellis Island", "why": "Ferry to the harbour's icons", "tags": []},
            {"name": "Brooklyn Bridge & DUMBO", "why": "Walk the bridge for skyline views", "tags": []},
            {"name": "Greenwich Village & Lower East Side", "why": "Music, bars and late-night dining", "tags": ["nightlife", "old-town"]},
        ],
        "adventures": [
            {"name": "Walk the High Line", "why": "Elevated park through west Manhattan", "tags": []},
            {"name": "See a Broadway show", "why": "World-class theatre in Midtown", "tags": ["nightlife"]},
            {"name": "Rooftop bars", "why": "Skyline cocktails across the city", "tags": ["rooftop-bar", "nightlife"]},
            {"name": "Tasting-menu dining", "why": "Some of the world's best restaurants", "tags": ["michelin-nearby"]},
        ],
        "tips": ["Subway is the fastest way around.", "Book theatre and top restaurants early."],
    },
    "TLV": {
        "name": "Tel Aviv & Jerusalem, Israel",
        "months": [3, 3, 5, 5, 5, 4, 3, 3, 4, 5, 5, 3],
        "season_note": "March-May and October-November are warm and pleasant. "
                       "July-August is hot and humid, though ideal for the beach.",
        "places": [
            {"name": "White City & Bauhaus quarter", "why": "UNESCO-listed architecture in central Tel Aviv", "tags": ["old-town"]},
            {"name": "Jaffa Old Port", "why": "Ancient harbour with markets and galleries", "tags": ["old-town", "beachfront"]},
            {"name": "Carmel Market & Sarona", "why": "Fresh food, street eats and chef-led restaurants", "tags": ["michelin-nearby"]},
            {"name": "Tel Aviv beaches", "why": "Long promenade and lively beach bars", "tags": ["beachfront", "nightlife"]},
        ],
        "adventures": [
            {"name": "Day trip to Jerusalem", "why": "The Old City is under an hour away", "tags": ["old-town"], "photo_query": "Old City of Jerusalem"},
            {"name": "Float in the Dead Sea", "why": "Mineral spas and desert scenery", "tags": ["spa"], "photo_query": "Dead Sea"},
            {"name": "Sunset promenade walk", "why": "From Jaffa to the marina along the sea", "tags": ["beachfront", "quiet"], "photo_query": "Tel Aviv beach promenade"},
            {"name": "Rooftop and club night", "why": "Tel Aviv's nightlife runs late", "tags": ["nightlife", "rooftop-bar"], "photo_query": "Tel Aviv skyline night"},
        ],
        "tips": ["Check current travel advisories before booking.", "Many places pause for Shabbat from Friday afternoon."],
    },
}


# ---------------------------------------------------------------------------
# Guide assembly: pure functions, no I/O, so they are unit-tested directly.
# ---------------------------------------------------------------------------
VERDICTS = [(4.5, "Ideal"), (3.5, "Good"), (2.5, "Fair"), (0.0, "Off-season")]


def _month_windows(months: list[int]) -> str:
    """[5, 6, 9, 10] -> 'May-Jun, Sep-Oct'; contiguous runs merge, Dec-Jan wraps."""
    if not months:
        return ""
    present = set(months)
    if len(present) == 12:
        return "Year-round"
    starts = [m for m in sorted(present) if ((m - 2) % 12) + 1 not in present]
    runs = []
    for s in starts:
        end, n = s, s
        while (n % 12) + 1 in present:
            n = (n % 12) + 1
            end = n
        first, last = calendar.month_abbr[s], calendar.month_abbr[end]
        runs.append(first if s == end else f"{first}-{last}")
    return ", ".join(runs)


def assess_timing(scores: list[int], start: date, end: date) -> dict:
    """Average the monthly suitability over every day of the trip, and describe the
    destination's ideal and worst windows."""
    days = (end - start).days + 1
    trip_days = [start + timedelta(days=i) for i in range(max(days, 1))]
    score = sum(scores[d.month - 1] for d in trip_days) / len(trip_days)
    trip_months = sorted({d.month for d in trip_days}, key=lambda m: (m - start.month) % 12)

    top = max(scores)
    best = [m for m, s in enumerate(scores, start=1) if s == top]
    avoid = [m for m, s in enumerate(scores, start=1) if s <= 2]
    verdict = next(label for floor, label in VERDICTS if score >= floor)
    best_windows = _month_windows(best)

    suggestion = None
    if score < top - 0.75:
        suggestion = f"Conditions are better in {best_windows}. If your dates are flexible, consider moving the trip."

    return {
        "score": round(score, 2),
        "verdict": verdict,
        "trip_months": trip_months,
        "best_windows": best_windows,
        "avoid_windows": _month_windows(avoid),
        "suggestion": suggestion,
    }


def _distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    """Great-circle distance in metres (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return round(2 * 6371000 * math.asin(math.sqrt(a)))


def _venue(row: tuple) -> dict:
    """A demo venue plus a synthetic, deterministic discount (about 70% of venues have one)."""
    name, kind, lat, lng, price, rating, blurb = row
    h = zlib.crc32(name.encode())
    deal = None
    if h % 10 < 7:
        pct = 10 + h % 26
        deal = {"pct": pct, "typical_price": round(price / (1 - pct / 100))}
    return {"name": name, "kind": kind, "lat": lat, "lng": lng, "price": price, "rating": rating,
            "blurb": blurb, "deal": deal}


def _nearby(venues: list[dict], lat: float, lng: float, limit: int = 3, radius_m: int = 3000) -> list[dict]:
    found = [{**v, "distance_m": _distance_m(lat, lng, v["lat"], v["lng"])} for v in venues]
    found = [v for v in found if v["distance_m"] <= radius_m]
    return sorted(found, key=lambda v: v["distance_m"])[:limit]


def _with_matches(items: list[dict], interests: list[str], code: str = "", venues: list[dict] | None = None) -> list[dict]:
    extras = RICH.get(code, {}).get("items", {})
    out = []
    for i in items:
        item = {**i, "matches": [t for t in i["tags"] if t in interests]}
        extra = extras.get(i["name"])
        if extra:
            item.update(extra)
            item["nearby"] = _nearby(venues or [], extra["lat"], extra["lng"])
        out.append(item)
    return sorted(out, key=lambda i: -len(i["matches"]))  # stable: keeps curated order for ties


def build_guide(destination: str, start_date: str, end_date: str, interests: list[str] | None = None) -> dict:
    code = destination.strip().upper()
    guide = GUIDES.get(code)
    if guide is None:
        return {"found": False, "destination": code}

    interests = interests or []
    rich = RICH.get(code)
    venues = [_venue(row) for row in VENUES.get(code, [])]
    return {
        "found": True,
        "rich": rich is not None,
        "center": CITY_CENTERS.get(code),
        "hero": rich["hero"] if rich else None,
        "venues": venues,
        "destination": code,
        "name": guide["name"],
        "months": guide["months"],
        "season_note": guide["season_note"],
        "timing": assess_timing(guide["months"], date.fromisoformat(start_date), date.fromisoformat(end_date)),
        "places": _with_matches(guide["places"], interests, code, venues),
        "adventures": _with_matches(guide["adventures"], interests, code, venues),
        "tips": guide["tips"],
    }
