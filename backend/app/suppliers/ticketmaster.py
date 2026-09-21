"""Live events and parties from the Ticketmaster Discovery API (free key: developer.ticketmaster.com).

Enabled only when TICKETMASTER_API_KEY is set. Events are shown with a link to the official Ticketmaster
page and attributed to Ticketmaster. Results are cached for 30 minutes (the free tier is rate limited).

NOTE: parsing follows the documented response shape and is unit-tested on a sample payload, but it has not
been exercised against a live key.
"""
from datetime import date

from app.config import ticketmaster_key
from app.live.http import cached, get_json

URL = "https://app.ticketmaster.com/discovery/v2/events.json"
TTL = 1800


def enabled() -> bool:
    return ticketmaster_key() is not None


def _image(images: list[dict]) -> str | None:
    wide = [i for i in images if i.get("url") and i.get("ratio") == "16_9"]
    pool = wide or [i for i in images if i.get("url")]
    return min(pool, key=lambda i: abs((i.get("width") or 0) - 640))["url"] if pool else None


def parse_events(data: dict) -> list[dict]:
    out = []
    for e in (data.get("_embedded") or {}).get("events", []):
        start = (e.get("dates") or {}).get("start") or {}
        venue = ((e.get("_embedded") or {}).get("venues") or [{}])[0]
        loc = venue.get("location") or {}
        prices = (e.get("priceRanges") or [{}])[0]
        try:
            lat, lng = float(loc["latitude"]), float(loc["longitude"])
        except (KeyError, TypeError, ValueError):
            lat = lng = None
        if not e.get("name") or not start.get("localDate") or not e.get("url"):
            continue
        cls = (e.get("classifications") or [{}])[0]
        out.append({
            "id": f"tm-{e['id']}", "title": e["name"], "venue": venue.get("name"),
            "category": (cls.get("segment") or {}).get("name") or "Event",
            "date": start["localDate"], "time": (start.get("localTime") or "")[:5] or None,
            "url": e["url"], "photo_url": _image(e.get("images") or []),
            "price_min": prices.get("min"), "price_max": prices.get("max"), "currency": prices.get("currency"),
            "lat": lat, "lng": lng, "source": "ticketmaster",
        })
    return out


def _search(lat: float, lng: float, radius_km: int, start: date, end: date, size: int) -> list[dict]:
    key = f"tm_{round(lat, 2)}_{round(lng, 2)}_{radius_km}_{start}_{end}_{size}"

    def fetch():
        data = get_json(URL, {
            "apikey": ticketmaster_key(), "latlong": f"{lat},{lng}", "radius": radius_km, "unit": "km",
            "startDateTime": f"{start.isoformat()}T00:00:00Z", "endDateTime": f"{end.isoformat()}T23:59:59Z",
            "size": size, "sort": "date,asc",
        }, timeout=15)
        return parse_events(data)

    return cached(key, TTL, fetch)


def events_near(lat: float, lng: float, radius_km: int = 5, day: date | None = None, size: int = 20) -> list[dict]:
    """Events today (or on `day`) within radius_km. Used by the nearby engine."""
    day = day or date.today()
    return _search(lat, lng, radius_km, day, day, size)


def events_for_trip(lat: float, lng: float, start: date, end: date, radius_km: int = 20, size: int = 30) -> list[dict]:
    return _search(lat, lng, radius_km, start, end, size)
