"""Price ESTIMATES, used when no real price source (Amadeus) is configured.

These are deliberately simple, transparent models. Every price they produce is flagged
`price_source: "estimate"` and the UI labels it as such. They are NOT quotes.
"""
import zlib
from datetime import date

from app.live.geo import haversine_km

# Typical nightly price (GBP) for a 3-star room at each city price level
BASE_NIGHT = {1: 42, 2: 68, 3: 100, 4: 148}
STAR_FACTOR = {None: 1.0, 1: 0.55, 2: 0.7, 3: 1.0, 4: 1.55, 5: 2.5}


def _jitter(seed: str, spread: float) -> float:
    """Deterministic +/- spread so the same hotel always gets the same estimate."""
    return 1 + ((zlib.crc32(seed.encode()) % 2001) / 1000 - 1) * spread


def hotel_night_estimate(dest: dict, stars: int | None, season_score: int, name: str) -> int:
    season = 0.85 + 0.10 * (season_score - 1)  # better weather months are busier and dearer
    return round(BASE_NIGHT[dest["cost"]] * STAR_FACTOR[stars] * season * _jitter(name, 0.12))


def flight_options_estimate(origin: dict, dest: dict, depart: str, ret: str, travelers: int) -> list[dict]:
    """Five typical fare/route shapes for the distance, per traveler, return trip in economy."""
    km = haversine_km(origin["lat"], origin["lng"], dest["lat"], dest["lng"])
    month = int(depart[5:7])
    peak = 1.2 if month in (6, 7, 8, 12) else 1.0
    lead_days = (date.fromisoformat(depart) - date.today()).days
    urgency = 1.25 if lead_days < 14 else 1.0
    base = max(60, 30 + 0.075 * km) * peak * urgency
    fly_min = km / 820 * 60 + 40

    shapes = [  # label, stops, price factor, duration factor, extra minutes
        ("Direct, standard fare", 0, 1.00, 1.00, 0),
        ("Direct, flexible fare", 0, 1.25, 1.00, 0),
        ("1 stop, standard fare", 1, 0.82, 1.30, 90),
        ("1 stop, budget fare", 1, 0.72, 1.45, 130),
        ("2 stops, cheapest", 2, 0.66, 1.65, 210),
    ]
    out = []
    for i, (label, stops, pf, df, extra) in enumerate(shapes):
        if stops == 0 and km > 11500:  # no nonstop flights exist beyond about this range
            continue
        if stops == 2 and km < 4000:
            continue
        price = round(base * pf * _jitter(f"{origin['code']}{dest['code']}{i}", 0.05))
        out.append({
            "id": f"FL-EST-{origin['code']}-{dest['code']}-{i}",
            "airline": label,
            "origin": origin["code"], "destination": dest["code"],
            "depart_date": depart, "return_date": ret,
            "stops": stops,
            "duration_minutes": round(fly_min * df + extra),
            "depart_time": None,
            "price_per_traveler": price,
            "total_price": price * travelers,
            "currency": "GBP",
            "price_source": "estimate",
        })
    return out
