"""Recent real flight fares from the Travelpayouts (Aviasales) Data API, free after an affiliate signup.

Enabled only when TRAVELPAYOUTS_TOKEN is set. These are CACHED fares that other travelers found in the last
couple of days, not live quotes, so they are labelled "Recent fares" and never "Live". Airlines come back as
IATA codes, which are shown as they are.

NOTE: parsing follows the documented response shape and is unit-tested on a sample payload, but it has not
been exercised against a live token.
"""
from app.config import travelpayouts_token
from app.live.http import cached, get_json

URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
TTL = 3600


def enabled() -> bool:
    return travelpayouts_token() is not None


def parse_fares(data: dict, origin: str, dest: str, depart: str, ret: str, adults: int) -> list[dict]:
    out = []
    for i, f in enumerate(data.get("data") or []):
        price = f.get("price")
        if not price or not f.get("airline"):
            continue
        depart_at = f.get("departure_at") or ""
        duration = f.get("duration_to") or (f.get("duration") or 0)
        out.append({
            "id": f"FL-TP-{i}-{f['airline']}-{depart_at[:10]}",
            "airline": f["airline"],
            "origin": origin, "destination": dest, "depart_date": depart, "return_date": ret,
            "stops": int(f.get("transfers") or 0),
            "duration_minutes": int(duration),
            "depart_time": depart_at[11:16] or "00:00",
            "price_per_traveler": round(float(price)),
            "total_price": round(float(price)) * adults,
            "currency": (data.get("currency") or "GBP").upper(),
            "price_source": "travelpayouts",
        })
    return out


def flight_fares(origin: str, dest: str, depart: str, ret: str, adults: int, currency: str = "gbp") -> list[dict]:
    def fetch():
        return get_json(URL, {
            "origin": origin, "destination": dest, "departure_at": depart, "return_at": ret,
            "one_way": "false", "sorting": "price", "cur": currency, "limit": 8, "unique": "false",
            "token": travelpayouts_token(),
        }, timeout=15)

    data = cached(f"tp_{origin}_{dest}_{depart}_{ret}_{currency}", TTL, fetch)
    return parse_fares(data, origin, dest, depart, ret, adults)
