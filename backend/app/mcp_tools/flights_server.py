import random

from mcp.server.fastmcp import FastMCP

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

    Mock provider standing in for a real Amadeus/Skyscanner-style search — prices and
    times are randomized on every call, so re-invoking the tool (the user pressing
    "refresh") naturally yields a new plan.
    """
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
