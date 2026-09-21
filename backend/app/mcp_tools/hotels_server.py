import math
import random
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/, so `app.*` imports work when run as a script
from app import config  # noqa: E402
from app.live import travel  # noqa: E402
from app.mcp_tools.guides_rich import CITY_CENTERS  # noqa: E402

mcp = FastMCP("hotels")

HOTEL_PREFIXES = ["Grand", "Villa", "The", "Casa", "Palazzo", "Hotel", "Riviera", "Bellavista"]
HOTEL_SUFFIXES = ["Marina", "Terrace", "Gardens", "Plaza", "Bay", "Suites", "Reale", "Costa"]

TAG_POOL = [
    "beachfront", "nightlife", "michelin-nearby", "supercar-rental-nearby",
    "spa", "family-friendly", "old-town", "rooftop-bar", "quiet", "pet-friendly",
]


STAY_PHOTOS = [f"stay-{n}" for n in range(1, 7)]  # generic, illustrative photos (the demo hotels are fictional)
AMENITY_POOL = ["Free Wi-Fi", "Air conditioning", "Breakfast included", "Pool", "Gym", "Airport shuttle", "24h reception"]
TAG_AMENITIES = {"spa": "Spa", "beachfront": "Beachfront", "rooftop-bar": "Rooftop bar", "pet-friendly": "Pet friendly",
                 "family-friendly": "Family rooms", "nightlife": "Nightlife nearby", "quiet": "Quiet location"}


def _clamp_rating(value: float) -> float:
    return round(max(1.0, min(5.0, value)), 1)


def _enrich(hotel: dict, destination: str, index: int = 0) -> dict:
    """Demo-only extras for the visual UI: photos, coordinates, rating breakdown, amenities and a
    synthetic deal + 30-day price history. None of this comes from a real provider."""
    price, rating, dist = hotel["price_per_night"], hotel["rating"], hotel["distance_to_center_km"]

    center = CITY_CENTERS.get(destination.strip().upper())
    if center:
        bearing = random.uniform(0, 2 * math.pi)
        hotel["lat"] = round(center[0] + (dist / 111.0) * math.cos(bearing), 5)
        hotel["lng"] = round(center[1] + (dist / (111.0 * math.cos(math.radians(center[0])))) * math.sin(bearing), 5)

    # Vary the lead photo across the result list so the cards do not all look alike.
    lead = STAY_PHOTOS[index % len(STAY_PHOTOS)]
    hotel["photos"] = [lead] + random.sample([p for p in STAY_PHOTOS if p != lead], 2)
    hotel["reviews"] = random.randint(120, 4800)
    hotel["rating_breakdown"] = {
        "Cleanliness": _clamp_rating(rating + random.uniform(-0.4, 0.3)),
        "Location": _clamp_rating(rating + 0.4 - dist * 0.12 + random.uniform(-0.2, 0.2)),
        "Service": _clamp_rating(rating + random.uniform(-0.3, 0.3)),
        "Value": _clamp_rating(rating + random.uniform(-0.5, 0.2)),
    }
    from_tags = [TAG_AMENITIES[t] for t in hotel["tags"] if t in TAG_AMENITIES]
    extras = random.sample(AMENITY_POOL, random.randint(3, 4))
    hotel["amenities"] = list(dict.fromkeys(from_tags + extras))

    deal = None
    typical = price
    if random.random() < 0.65:
        pct = random.randint(8, 32)
        typical = round(price / (1 - pct / 100))
        deal = {"pct": pct, "typical_price": typical}
    hotel["deal"] = deal
    history = []
    for day in range(30):
        drift = typical + (price - typical) * (day / 29)
        history.append(round(drift * random.uniform(0.96, 1.04)))
    history[-1] = price
    hotel["price_history"] = history
    return hotel


@mcp.tool()
def search_hotels(
    destination: str,
    check_in: str,
    check_out: str,
    travelers: int = 1,
    interests: list[str] | None = None,
) -> dict:
    """Search hotel options in a destination for given check-in/check-out dates.

    For catalog cities: REAL hotels from OpenStreetMap (names, star class, amenities, neighbourhood
    signals), priced by Amadeus if configured, otherwise by clearly-labelled ESTIMATES. Falls back to
    randomised demo data when offline or if the live sources fail. `source` says which:
    "amadeus", "estimate" or "demo".
    """
    if not config.offline():
        try:
            live = travel.search_hotels(destination, check_in, check_out, travelers)
            if live:
                return {**live, "query": {**live["query"], "interests": interests or []}}
        except Exception:
            pass  # fall through to the demo generator
    result = _demo_hotels(destination, check_in, check_out, travelers, interests)
    return {**result, "source": "demo", "detail": "Simulated demo data"}


def _demo_hotels(destination: str, check_in: str, check_out: str, travelers: int, interests: list[str] | None) -> dict:
    interests = interests or []
    count = random.randint(5, 8)

    options = []
    for i in range(count):
        price_per_night = random.randint(60, 420)
        rating = round(random.uniform(3.2, 5.0), 1)

        guaranteed_matches = [tag for tag in interests if random.random() < 0.5]
        extra_pool = TAG_POOL.copy()
        random.shuffle(extra_pool)
        extra_tags = extra_pool[: random.randint(1, 3)]
        tags = list(dict.fromkeys([*guaranteed_matches, *extra_tags]))

        options.append(_enrich({
            "id": f"HT-{destination}-{i}-{random.randint(1000, 9999)}",
            "name": f"{random.choice(HOTEL_PREFIXES)} {random.choice(HOTEL_SUFFIXES)}",
            "destination": destination,
            "check_in": check_in,
            "check_out": check_out,
            "price_per_night": price_per_night,
            "rating": rating,
            "tags": tags,
            "distance_to_center_km": round(random.uniform(0.1, 8), 1),
            "currency": "GBP",
            "travelers": travelers,
        }, destination, i))

    return {
        "query": {
            "destination": destination,
            "check_in": check_in,
            "check_out": check_out,
            "travelers": travelers,
            "interests": interests,
        },
        "options": options,
    }


if __name__ == "__main__":
    mcp.run()
