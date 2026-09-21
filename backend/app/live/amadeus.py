"""Optional REAL flight and hotel offers from Amadeus Self-Service (free signup at developers.amadeus.com).

Enabled only when AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET are set. The free "test" environment
returns a limited, cached subset of real inventory, so some routes and cities return nothing; callers
fall back to price estimates in that case.

NOTE: parsing follows Amadeus' documented response shapes and is covered by unit tests on sample
payloads, but it has not been exercised against live credentials.
"""
import re
import time
from datetime import date

from app.config import amadeus_base_url, amadeus_credentials
from app.live.http import client

_token = {"value": None, "expires": 0.0}


def enabled() -> bool:
    return amadeus_credentials() is not None


def _bearer() -> str:
    if _token["value"] and time.time() < _token["expires"] - 30:
        return _token["value"]
    cid, secret = amadeus_credentials()
    with client(20) as c:
        r = c.post(f"{amadeus_base_url()}/v1/security/oauth2/token", data={
            "grant_type": "client_credentials", "client_id": cid, "client_secret": secret,
        })
        r.raise_for_status()
        body = r.json()
    _token.update(value=body["access_token"], expires=time.time() + int(body.get("expires_in", 1799)))
    return _token["value"]


def _get(path: str, params: dict) -> dict:
    with client(40) as c:
        r = c.get(f"{amadeus_base_url()}{path}", params=params, headers={"Authorization": f"Bearer {_bearer()}"})
        r.raise_for_status()
        return r.json()


def parse_duration(iso: str) -> int:
    """'PT7H35M' -> 455 minutes."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", iso or "")
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0) if m else 0


def parse_flight_offers(data: dict, origin: str, dest: str, depart: str, ret: str, adults: int) -> list[dict]:
    carriers = data.get("dictionaries", {}).get("carriers", {})
    out = []
    for i, offer in enumerate(data.get("data", [])):
        outbound = offer["itineraries"][0]
        segments = outbound["segments"]
        code = (offer.get("validatingAirlineCodes") or [segments[0]["carrierCode"]])[0]
        total = float(offer["price"]["grandTotal"])
        out.append({
            "id": f"FL-AMA-{offer.get('id', i)}",
            "airline": carriers.get(code, code),
            "origin": origin, "destination": dest, "depart_date": depart, "return_date": ret,
            "stops": len(segments) - 1,
            "duration_minutes": parse_duration(outbound.get("duration", "")),
            "depart_time": segments[0]["departure"]["at"][11:16],
            "price_per_traveler": round(total / adults),
            "total_price": round(total),
            "currency": offer["price"].get("currency", "GBP"),
            "price_source": "amadeus",
        })
    return out


def flight_offers(origin: str, dest: str, depart: str, ret: str, adults: int, currency: str = "GBP") -> list[dict]:
    data = _get("/v2/shopping/flight-offers", {
        "originLocationCode": origin, "destinationLocationCode": dest, "departureDate": depart,
        "returnDate": ret, "adults": adults, "currencyCode": currency, "max": 8,
    })
    return parse_flight_offers(data, origin, dest, depart, ret, adults)


def parse_hotel_offers(data: dict, nights: int) -> list[dict]:
    out = []
    for item in data.get("data", []):
        offers = item.get("offers") or []
        hotel = item.get("hotel", {})
        if not offers or "latitude" not in hotel:
            continue
        price = offers[0]["price"]
        out.append({
            "hotel_id": hotel.get("hotelId"), "name": hotel.get("name", "").title(),
            "lat": hotel["latitude"], "lng": hotel["longitude"],
            "price_per_night": round(float(price.get("total", 0)) / max(1, nights)),
            "currency": price.get("currency", "GBP"),
            "rating": float(hotel["rating"]) if str(hotel.get("rating", "")).replace(".", "").isdigit() else None,
        })
    return out


def hotel_offers(city_code: str, check_in: str, check_out: str, adults: int, currency: str = "GBP") -> list[dict]:
    listing = _get("/v1/reference-data/locations/hotels/by-city", {"cityCode": city_code, "radius": 8, "radiusUnit": "KM"})
    ids = [h["hotelId"] for h in listing.get("data", [])[:20]]
    if not ids:
        return []
    data = _get("/v3/shopping/hotel-offers", {
        "hotelIds": ",".join(ids), "adults": adults, "checkInDate": check_in, "checkOutDate": check_out,
        "currency": currency, "bestRateOnly": "true",
    })
    nights = (date.fromisoformat(check_out) - date.fromisoformat(check_in)).days
    return parse_hotel_offers(data, nights)
