"""Live flight and stay search: Amadeus when configured, otherwise real OpenStreetMap hotels with
clearly-labelled price estimates. Returns the same shapes the demo servers return, plus source labels."""
from datetime import date

from app.live import amadeus, catalog, climate, osm, pricing
from app.live.geo import haversine_km
from app.suppliers import travelpayouts


def search_flights(origin: str, destination: str, depart: str, ret: str, travelers: int) -> dict | None:
    """None when either end is not in the catalog (the caller then uses demo data)."""
    o, d = catalog.resolve(origin), catalog.resolve(destination)
    if not o or not d or o["code"] == d["code"]:
        return None
    options, source, detail = None, "estimate", "Typical fares estimated from distance and season. Not a quote."
    if amadeus.enabled():
        try:
            options = amadeus.flight_offers(o["code"], d["code"], depart, ret, travelers) or None
            if options:
                source, detail = "amadeus", "Real offers from Amadeus Self-Service"
        except Exception:
            options = None
    if not options and travelpayouts.enabled():
        try:
            options = travelpayouts.flight_fares(o["code"], d["code"], depart, ret, travelers) or None
            if options:
                source, detail = "travelpayouts", "Recent fares found by travelers (Aviasales via Travelpayouts). Cached, so not a live quote."
        except Exception:
            options = None
    if not options:
        options = pricing.flight_options_estimate(o, d, depart, ret, travelers)
    return {
        "query": {"origin": o["code"], "destination": d["code"], "depart_date": depart, "return_date": ret, "travelers": travelers},
        "options": options, "source": source, "detail": detail,
    }


def _season_score(dest: dict, check_in: str) -> int:
    try:
        return climate.monthly_climate(dest)["scores"][int(check_in[5:7]) - 1]
    except Exception:
        return 3


def _hotel_record(base: dict, dest: dict, check_in: str, check_out: str, travelers: int, price: int, price_source: str) -> dict:
    return {
        **base,
        "check_in": check_in, "check_out": check_out, "travelers": travelers,
        "price_per_night": price, "price_source": price_source, "currency": "GBP",
        "rating": None,  # OpenStreetMap has star class but no guest reviews; Amadeus may set this later
        "live": True,
    }


def search_hotels(destination: str, check_in: str, check_out: str, travelers: int) -> dict | None:
    dest = catalog.resolve(destination)
    if not dest:
        return None
    real = osm.real_hotels(dest, 8)
    if not real:
        return None
    area_note = osm.area(dest)["source"]

    if amadeus.enabled():
        try:
            offers = amadeus.hotel_offers(dest["code"], check_in, check_out, travelers)
        except Exception:
            offers = []
        if len(offers) >= 3:
            hotels = []
            for o in offers[:8]:
                dist = haversine_km(dest["lat"], dest["lng"], o["lat"], o["lng"])
                bars, food, beach = osm.signals_at(dest, (o["lat"], o["lng"]))
                base = {
                    "id": f"ama-{o['hotel_id']}", "name": o["name"], "destination": dest["code"], "kind": "hotel",
                    "stars": None, "lat": o["lat"], "lng": o["lng"], "distance_to_center_km": round(dist, 1),
                    "address": None, "website": None, "osm_url": None, "amenities": [],
                    "tags": osm.interest_tags(dist, bars, food, beach, {"name": o["name"]}),
                    "signals": {"bars_300m": bars, "restaurants_300m": food, "beach_m": beach},
                }
                rec = _hotel_record(base, dest, check_in, check_out, travelers, o["price_per_night"], "amadeus")
                rec["rating"] = o["rating"]
                hotels.append(rec)
            return {
                "query": {"destination": dest["code"], "check_in": check_in, "check_out": check_out, "travelers": travelers},
                "options": hotels, "source": "amadeus",
                "detail": f"Real offers from Amadeus Self-Service; neighbourhood data from {area_note}",
            }

    season = _season_score(dest, check_in)
    hotels = [
        _hotel_record(h, dest, check_in, check_out, travelers,
                      pricing.hotel_night_estimate(dest, h["stars"], season, h["name"]), "estimate")
        for h in real
    ]
    return {
        "query": {"destination": dest["code"], "check_in": check_in, "check_out": check_out, "travelers": travelers},
        "options": hotels, "source": "estimate",
        "detail": f"Real hotels from {area_note}. Nightly prices are estimates (star rating, city price level, season), not quotes.",
    }
