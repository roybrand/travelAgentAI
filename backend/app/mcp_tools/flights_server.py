import random
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/, so `app.*` imports work when run as a script
from app import config  # noqa: E402
from app.live import travel  # noqa: E402

mcp = FastMCP("flights")

AIRLINES = [
    "BlueSky Air", "Meridian Airlines", "Solara Airways", "Northwind Air",
    "Coastal Jet", "Vantage Airlines", "Aurora Air", "Skyline Express",
]


@mcp.tool()
def search_flights(
    origin: str,
    destination: str,
    depart_date: str,
    return_date: str,
    travelers: int = 1,
) -> dict:
    """Search round-trip flight options between an origin and destination for given dates.

    Uses real Amadeus offers when credentials are configured, otherwise labelled price ESTIMATES from
    distance and season. Falls back to randomised demo data when offline or for unknown airports.
    The result's `source` says which: "amadeus", "estimate" or "demo".
    """
    if not config.offline():
        try:
            live = travel.search_flights(origin, destination, depart_date, return_date, travelers)
            if live:
                return live
        except Exception:
            pass  # fall through to the demo generator
    result = _demo_flights(origin, destination, depart_date, return_date, travelers)
    return {**result, "source": "demo", "detail": "Simulated demo data"}


def _demo_flights(origin: str, destination: str, depart_date: str, return_date: str, travelers: int) -> dict:
    count = random.randint(4, 6)
    options = []
    for i in range(count):
        base_price = random.randint(80, 650)
        stops = random.choice([0, 0, 1, 1, 2])
        duration_minutes = random.randint(90, 780) + stops * random.randint(45, 120)
        depart_hour = random.randint(0, 23)
        depart_minute = random.choice([0, 15, 30, 45])

        options.append({
            "id": f"FL-{depart_date}-{i}-{random.randint(1000, 9999)}",
            "airline": random.choice(AIRLINES),
            "origin": origin,
            "destination": destination,
            "depart_date": depart_date,
            "return_date": return_date,
            "stops": stops,
            "duration_minutes": duration_minutes,
            "depart_time": f"{depart_hour:02d}:{depart_minute:02d}",
            "price_per_traveler": base_price,
            "total_price": base_price * travelers,
            "currency": "GBP",
        })

    return {
        "query": {
            "origin": origin,
            "destination": destination,
            "depart_date": depart_date,
            "return_date": return_date,
            "travelers": travelers,
        },
        "options": options,
    }


if __name__ == "__main__":
    mcp.run()
