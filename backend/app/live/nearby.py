"""Dynamic "near you right now" recommendations from a GPS position, the weather, the time of day,
the traveler's interests and their trip plan. Opt-in: the browser only calls this after the user turns
the feature on.

Data (all free, no keys): Wikipedia sights around the point, OpenStreetMap places to eat and drink,
Open-Meteo current weather and short-range rain forecast. Also reviewed partner deals from our own database
and, when a free Ticketmaster key is set, live events.

Privacy: coordinates are used only to look things up. They are rounded when used as cache keys, and the
runtime log (backend/logs/dynamic-features.md) records rule names and the nearest city, never coordinates.

Every ranking rule has a stable ID (see RULES). docs/FEATURES.md must list each one; a test enforces it.
"""
import math
import re
from datetime import datetime, timezone

from app.config import ROOT
from app.live import catalog, osm, places
from app.live.geo import haversine_m
from app.live.http import cached, get_json
from app.partners import deals as partner_deals
from app.suppliers import ticketmaster

LOG_PATH = ROOT / "logs" / "dynamic-features.md"
WALK_M_PER_MIN = 80

# rule id -> what it does. Documented in docs/FEATURES.md (a test keeps the two in sync).
RULES = {
    "DYN-01": "Plan proximity: something from your trip plan is close to you right now",
    "DYN-02": "Rain expected or falling: indoor places are pushed up, open-air places down",
    "DYN-03": "Good weather: parks, viewpoints and waterfronts are pushed up",
    "DYN-04": "Breakfast time: cafes are pushed up",
    "DYN-05": "Lunch time: restaurants are pushed up",
    "DYN-06": "Evening: restaurants and bars are pushed up (bars more if you like nightlife)",
    "DYN-07": "Interest match: places that fit what you said you like are pushed up",
    "DYN-08": "Distance: nearer places rank higher, with a walking-time estimate",
    "DYN-09": "Popularity: among sights, more-read Wikipedia articles rank higher",
    "DYN-10": "No repeats: the app only pushes a recommendation it has not already shown this session",
    "DYN-11": "Partner deal in reach: a reviewed partner deal nearby ranks by interest match, real discount and distance, never by payment, and is always labelled",
    "DYN-12": "Ends soon: a deal ending today or tomorrow is nudged up a little, as information rather than pressure",
    "DYN-13": "Live event: an event starting within the next few hours close to you (needs a free Ticketmaster key)",
}

INDOOR = re.compile(r"museum|gallery|church|cathedral|basilica|palace|theat|opera|market hall|library|aquarium|temple|mosque|castle|synagogue|hall", re.I)
OUTDOOR = re.compile(r"park|garden|beach|viewpoint|square|plaza|piazza|bridge|waterfront|promenade|island|lake|hill|tower|riverside|boulevard", re.I)


def _r(v: float) -> float:
    return round(v, 3)  # about 100 m: enough for caching without keeping a precise location


# ---------------------------------------------------------------- data fetching (cached)

def fetch_weather(lat: float, lng: float) -> dict:
    def fetch():
        d = get_json("https://api.open-meteo.com/v1/forecast", {
            "latitude": lat, "longitude": lng, "timezone": "auto", "forecast_hours": 3,
            "current": "temperature_2m,precipitation", "hourly": "precipitation_probability",
        }, timeout=15)
        probs = [p for p in d.get("hourly", {}).get("precipitation_probability", []) if p is not None]
        cur = d["current"]
        return {
            "temp_c": cur.get("temperature_2m"),
            "raining": (cur.get("precipitation") or 0) >= 0.2,
            "rain_soon": bool(probs) and max(probs) >= 50,
            "local_hour": int(cur["time"][11:13]),
            "local_time": cur["time"],
        }
    return cached(f"nearby_wx_{_r(lat)}_{_r(lng)}", 600, fetch)


def fetch_sights(lat: float, lng: float, radius_m: int) -> list[dict]:
    def fetch():
        pages = places._candidates_at(lat, lng, min(radius_m, 10000))
        ranked = sorted(pages, key=places._score, reverse=True)
        top = [p for p in ranked if places._score(p) >= 2.5][:12]
        creds = places.credits_for([p.get("pageimage") for p in top if p.get("pageimage")])
        out = []
        for p in top:
            cred = creds.get(places._norm(p.get("pageimage", "")))
            c = (p.get("coordinates") or [{}])[0]
            if c.get("lat") is None:
                continue
            out.append({
                "id": f"wp-{p['pageid']}", "name": p["title"], "why": p.get("description", ""),
                "lat": c["lat"], "lng": c["lon"], "url": f"https://en.wikipedia.org/?curid={p['pageid']}",
                "views_30d": sum(v or 0 for v in (p.get("pageviews") or {}).values()),
                "photo_url": p["thumbnail"]["source"] if cred else None, "photo_credit": cred,
                "tags": places.classify(f"{p['title']} {p.get('description', '')}"),
            })
        return out
    return cached(f"nearby_sights_{_r(lat)}_{_r(lng)}_{radius_m}", 3600, fetch)


def fetch_food(lat: float, lng: float) -> list[dict]:
    """Restaurants, cafes and bars within about 700 m. Overpass first; Nominatim if it is busy."""
    def fetch():
        q = (
            "[out:json][timeout:15];"
            f'nwr["amenity"~"^(restaurant|cafe|bar|pub)$"]["name"](around:700,{lat},{lng});out center tags 80;'
        )
        try:
            data = osm._overpass(q)["elements"]
            return [
                {"id": f"osm-{e['type']}-{e['id']}", "name": e["tags"]["name"], "amenity": e["tags"]["amenity"],
                 "cuisine": e["tags"].get("cuisine", ""), "lat": pt[0], "lng": pt[1],
                 "website": e["tags"].get("website") or e["tags"].get("contact:website")}
                for e in data if (pt := osm._pt(e))
            ]
        except Exception:
            out, here = [], {"lat": lat, "lng": lng}
            for word, amenity in (("restaurant", "restaurant"), ("cafe", "cafe")):
                for it in osm._nominatim(here, word):
                    if it.get("type") == amenity and it.get("name"):
                        out.append({"id": f"osm-{it['osm_type']}-{it['osm_id']}", "name": it["name"], "amenity": amenity,
                                    "cuisine": (it.get("extratags") or {}).get("cuisine", ""),
                                    "lat": float(it["lat"]), "lng": float(it["lon"]), "website": None})
            return out
    return cached(f"nearby_food_{_r(lat)}_{_r(lng)}", 3600, fetch)


# ---------------------------------------------------------------- ranking (pure)

def _walk(distance_m: int) -> str:
    mins = max(1, round(distance_m / WALK_M_PER_MIN))
    return f"{mins} min walk"


def _is_indoor(text: str) -> bool | None:
    if INDOOR.search(text):
        return True
    if OUTDOOR.search(text):
        return False
    return None


def _day_part(hour: int) -> str | None:
    if 7 <= hour <= 10:
        return "breakfast"
    if 11 <= hour <= 14:
        return "lunch"
    if 17 <= hour <= 22:
        return "evening"
    return None


def _event_start_hour(ev: dict) -> int | None:
    return int(ev["time"][:2]) if ev.get("time") else None


def recommend(pos: tuple[float, float], weather: dict, sights: list[dict], food: list[dict],
              planned: list[dict], interests: list[str], radius_m: int = 1500, limit: int = 10,
              deals: list[dict] = (), events: list[dict] = ()) -> list[dict]:
    """Pure ranking. Returns recommendations sorted best first, each with the rule IDs that fired."""
    bad_weather = bool(weather.get("raining") or weather.get("rain_soon"))
    warm_clear = not bad_weather and weather.get("temp_c") is not None and 14 <= weather["temp_c"] <= 31
    part = _day_part(weather.get("local_hour", 12))
    recs = []

    for it in planned:
        if it.get("lat") is None:
            continue
        d = haversine_m(pos[0], pos[1], it["lat"], it["lng"])
        if d <= 3000:
            recs.append({
                "id": f"plan-{it['name']}", "kind": "plan", "title": it["name"], "distance_m": d,
                "reason": f"On your trip plan and only a {_walk(d)} away", "rules": ["DYN-01", "DYN-08"],
                "score": 3.0 - d / 3000, "lat": it["lat"], "lng": it["lng"], "category": "plan",
            })

    for s in sights:
        d = haversine_m(pos[0], pos[1], s["lat"], s["lng"])
        if d > radius_m:
            continue
        rules, reasons = ["DYN-08"], [f"{_walk(d)} away"]
        score = 1.0 - 0.5 * d / radius_m
        text = f"{s['name']} {s.get('why', '')}"
        indoor = _is_indoor(text)
        if bad_weather and indoor:
            score += 0.45; rules.append("DYN-02"); reasons.insert(0, "Rain expected: a good indoor pick")
        elif bad_weather and indoor is False:
            score -= 0.5
        elif warm_clear and indoor is False:
            score += 0.3; rules.append("DYN-03"); reasons.insert(0, "Good weather for being outside")
        hits = [t for t in s.get("tags", []) if t in interests]
        if hits:
            score += 0.35 * min(2, len(hits)); rules.append("DYN-07"); reasons.append("Matches your interests")
        score += min(0.3, math.log10(1 + s.get("views_30d", 0)) / 12); rules.append("DYN-09")
        recs.append({
            "id": s["id"], "kind": "sight", "title": s["name"], "subtitle": s.get("why", ""), "distance_m": d,
            "reason": " · ".join(reasons), "rules": rules, "score": score, "lat": s["lat"], "lng": s["lng"],
            "photo_url": s.get("photo_url"), "photo_credit": s.get("photo_credit"), "url": s.get("url"),
            "category": "indoor" if indoor else "outdoor" if indoor is False else "sight",
        })

    for f in food:
        d = haversine_m(pos[0], pos[1], f["lat"], f["lng"])
        if d > min(radius_m, 800):
            continue
        rules, reasons = ["DYN-08"], [f"{_walk(d)} away"]
        score = 0.8 - 0.5 * d / 800
        amenity = f["amenity"]
        if part == "breakfast" and amenity == "cafe":
            score += 0.5; rules.append("DYN-04"); reasons.insert(0, "Breakfast time")
        elif part == "lunch" and amenity == "restaurant":
            score += 0.5; rules.append("DYN-05"); reasons.insert(0, "Lunch time")
        elif part == "evening" and amenity in ("restaurant", "bar", "pub"):
            boost = 0.5 if amenity == "restaurant" or "nightlife" in interests else 0.15
            score += boost; rules.append("DYN-06"); reasons.insert(0, "Good for this evening")
        elif part is None and amenity == "cafe":
            score += 0.2
        if amenity in ("bar", "pub") and "nightlife" in interests:
            score += 0.2; rules.append("DYN-07")
        cuisine = f["cuisine"].replace("_", " ").replace(";", ", ").capitalize() if f["cuisine"] else amenity.capitalize()
        recs.append({
            "id": f["id"], "kind": "food", "title": f["name"], "subtitle": cuisine, "distance_m": d,
            "reason": " · ".join(reasons), "rules": rules, "score": score, "lat": f["lat"], "lng": f["lng"],
            "url": f.get("website"), "category": amenity,
        })

    for dl in deals:
        if dl.get("lat") is None:
            continue
        d = haversine_m(pos[0], pos[1], dl["lat"], dl["lng"])
        if d > radius_m:
            continue
        rules, reasons = ["DYN-11", "DYN-08"], [f"{_walk(d)} away"]
        score = 0.9 - 0.5 * d / radius_m
        hits = sorted(partner_deals.deal_tags(dl) & set(interests))
        if hits:
            score += 0.35 * min(2, len(hits)); rules.append("DYN-07"); reasons.insert(0, "Matches your interests")
        if dl["discount_pct"] >= 10:
            score += min(0.5, dl["discount_pct"] / 100); reasons.insert(0, f"{dl['discount_pct']}% below the usual price")
        if partner_deals.ends_within(dl, 1):
            score += 0.1; rules.append("DYN-12"); reasons.append("Ends today" if dl["days_left"] == 0 else "Ends tomorrow")
        recs.append({
            "id": f"deal-{dl['id']}", "kind": "deal", "title": dl["title"], "subtitle": dl["description"][:140],
            "distance_m": d, "reason": " · ".join(reasons), "rules": rules, "score": score,
            "lat": dl["lat"], "lng": dl["lng"], "url": dl["url"], "photo_url": dl.get("photo_url"),
            "category": dl["category"], "deal_id": dl["id"], "partner": True, "partner_name": dl["partner_name"],
            "price": dl["price"], "reference_price": dl["reference_price"], "currency": dl["currency"],
            "discount_pct": dl["discount_pct"], "price_note": dl["price_note"], "valid_to": dl["valid_to"],
        })

    local_hour = weather.get("local_hour", 12)
    for ev in events:
        if ev.get("lat") is None:
            continue
        d = haversine_m(pos[0], pos[1], ev["lat"], ev["lng"])
        start_h = _event_start_hour(ev)
        if d > min(radius_m, 3000) or (start_h is not None and not local_hour - 1 <= start_h <= local_hour + 6):
            continue
        rules, reasons = ["DYN-13", "DYN-08"], [f"{_walk(d)} away"]
        score = 0.85 - 0.4 * d / min(radius_m, 3000)
        if start_h is not None and start_h - local_hour <= 3:
            score += 0.3
        reasons.insert(0, f"Today at {ev['time']}" if ev.get("time") else "On today")
        if ev["category"] == "Music" and "nightlife" in interests:
            score += 0.2; rules.append("DYN-07")
        recs.append({
            "id": ev["id"], "kind": "event", "title": ev["title"], "subtitle": ev.get("venue") or ev["category"],
            "distance_m": d, "reason": " · ".join(reasons), "rules": rules, "score": score,
            "lat": ev["lat"], "lng": ev["lng"], "url": ev["url"], "photo_url": ev.get("photo_url"),
            "category": "event", "attribution": "Ticketmaster", "price": ev.get("price_min"), "currency": ev.get("currency"),
        })

    recs.sort(key=lambda r: -r["score"])
    plan_recs = [r for r in recs if r["kind"] == "plan"][:3]
    others = [r for r in recs if r["kind"] != "plan"]
    top_sights = [r for r in others if r["kind"] == "sight"][:4]
    top_food = [r for r in others if r["kind"] == "food"][:3]
    top_deals = [r for r in others if r["kind"] == "deal"][:3]
    top_events = [r for r in others if r["kind"] == "event"][:2]
    picked = sorted(plan_recs + top_sights + top_food + top_deals + top_events, key=lambda r: -r["score"])[:limit]
    for r in picked:
        r["score"] = round(r["score"], 3)
    return picked


# ---------------------------------------------------------------- orchestration + log

def nearest_city(lat: float, lng: float) -> str:
    best = min(catalog.DESTINATIONS, key=lambda d: haversine_m(lat, lng, d["lat"], d["lng"]))
    return best["city"] if haversine_m(lat, lng, best["lat"], best["lng"]) < 60000 else "(outside the catalog)"


def log_event(city: str, recs: list[dict], weather: dict, path=None) -> None:
    """Append one row to the runtime markdown log: which rules fired, never where the user is."""
    path = path or LOG_PATH
    counts: dict[str, int] = {}
    for r in recs:
        for rule in r["rules"]:
            counts[rule] = counts.get(rule, 0) + 1
    rules = ", ".join(f"{k} x{v}" for k, v in sorted(counts.items())) or "none"
    wx = "rain" if weather.get("raining") or weather.get("rain_soon") else "dry"
    row = f"| {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} | {city} | {wx}, hour {weather.get('local_hour', '?')} | {rules} | {len(recs)} |\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(
                "# Dynamic feature log\n\nGenerated at runtime by the nearby-recommendations feature. "
                "Rule IDs are defined in `docs/FEATURES.md`. No coordinates are ever written here.\n\n"
                "| time (UTC) | nearest city | conditions | rules fired | recommendations |\n|---|---|---|---|---|\n",
                encoding="utf-8",
            )
        with path.open("a", encoding="utf-8") as fh:
            fh.write(row)
    except OSError:
        pass  # logging must never break a request


def _finish(lat: float, lng: float, recs: list[dict], weather: dict, radius_m: int, notes: list[str]) -> dict:
    partner_deals.record_impressions([r["deal_id"] for r in recs if r["kind"] == "deal"])
    city = nearest_city(lat, lng)
    log_event(city, recs, weather)
    return {
        "context": {"city": city, "weather": weather or None, "day_part": _day_part(weather["local_hour"]) if weather else None, "radius_m": radius_m},
        "recommendations": recs, "notes": notes,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def run_local(lat: float, lng: float, interests: list[str], planned: list[dict], radius_m: int = 1500) -> dict:
    """Offline mode: no internet lookups, but the trip plan and our own partner deals still work."""
    recs = recommend((lat, lng), {}, [], [], planned, interests, radius_m, deals=partner_deals.near(lat, lng, radius_m))
    return _finish(lat, lng, recs, {}, radius_m, ["Offline mode: only your plan and partner deals are shown."])


def run(lat: float, lng: float, interests: list[str], planned: list[dict], radius_m: int = 1500) -> dict:
    weather = fetch_weather(lat, lng)
    sights, food, events, notes = [], [], [], []
    try:
        sights = fetch_sights(lat, lng, radius_m)
    except Exception:
        notes.append("Sights are temporarily unavailable.")
    try:
        food = fetch_food(lat, lng)
    except Exception:
        notes.append("Places to eat are temporarily unavailable.")
    if ticketmaster.enabled():
        try:
            events = ticketmaster.events_near(lat, lng, radius_km=max(1, min(radius_m, 3000) // 1000 + 1))
        except Exception:
            notes.append("Live events are temporarily unavailable.")
    recs = recommend((lat, lng), weather, sights, food, planned, interests, radius_m,
                     deals=partner_deals.near(lat, lng, radius_m), events=events)
    return _finish(lat, lng, recs, weather, radius_m, notes)
