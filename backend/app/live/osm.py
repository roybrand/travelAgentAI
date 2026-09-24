"""Real hotels, restaurants, bars and beaches from OpenStreetMap (free, no key).

OpenStreetMap has locations, names, star ratings and amenities, but NO prices and NO guest reviews, so
this module never invents either. Prices come from Amadeus (if configured) or the estimator.

Overpass gives the richest data but its free public servers are often busy, so if it fails we fall back to
Nominatim (fewer results, and no bar/beach signals), and callers fall back further to demo data.
"""
import re
import time

from app.live.geo import haversine_m
from app.live.http import DAY, cached, client, peek

MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
RADIUS = 3500


def _overpass(query: str) -> dict:
    last = None
    for url in MIRRORS:  # public servers are often busy: one quick attempt each, then fall back
        try:
            with client(24) as c:
                r = c.post(url, data={"data": query})
                r.raise_for_status()
                return r.json()
        except Exception as exc:
            last = exc
    raise RuntimeError(f"Overpass unavailable: {last}")


def _pt(el: dict) -> tuple[float, float] | None:
    if "lat" in el:
        return el["lat"], el["lon"]
    c = el.get("center")
    return (c["lat"], c["lon"]) if c else None


def _fetch_overpass(dest: dict) -> dict:
    """One combined request: hotels, beaches, bars/clubs (positions only) and restaurants with cuisine."""
    a = f"(around:{RADIUS},{dest['lat']},{dest['lng']})"
    beach = f"(around:6000,{dest['lat']},{dest['lng']})"
    q = (
        "[out:json][timeout:22];"
        f'nwr["tourism"~"^(hotel|guest_house|hostel|apartment|motel)$"]["name"]{a};out center tags 300;'
        f'nwr["natural"="beach"]{beach};out center tags 60;'
        f'nwr["amenity"~"^(bar|pub|nightclub)$"]{a};out skel center 900;'
        f'nwr["amenity"="restaurant"]["name"]["cuisine"]{a};out center tags 600;'
    )
    out = {"hotels": [], "beaches": [], "bars": [], "restaurants": [], "source": "OpenStreetMap (Overpass)"}
    for e in _overpass(q)["elements"]:
        pt, tags = _pt(e), e.get("tags")
        if not pt:
            continue
        if not tags:
            out["bars"].append(pt)
        elif tags.get("natural") == "beach":
            out["beaches"].append(pt)
        elif tags.get("amenity") == "restaurant":
            out["restaurants"].append({"name": tags["name"], "cuisine": tags.get("cuisine", ""), "pt": pt,
                                       "website": tags.get("website") or tags.get("contact:website")})
        elif "tourism" in tags:
            out["hotels"].append({"type": e["type"], "id": e["id"], "tags": tags, "pt": pt})
    return out


def _nominatim(dest: dict, query: str) -> list[dict]:
    d = 0.045  # about 5 km
    box = f"{dest['lng'] - d * 1.4},{dest['lat'] + d},{dest['lng'] + d * 1.4},{dest['lat'] - d}"
    with client(30) as c:
        r = c.get("https://nominatim.openstreetmap.org/search", params={
            "q": query, "format": "jsonv2", "limit": 40, "viewbox": box, "bounded": 1,
            "extratags": 1, "addressdetails": 1,
        })
        r.raise_for_status()
        time.sleep(1.1)  # Nominatim's usage policy: at most one request per second
        return r.json()


def _fetch_nominatim(dest: dict) -> dict:
    """Fallback when Overpass is down: fewer results, and no bar/beach signals."""
    hotels, restaurants = [], []
    for it in _nominatim(dest, "hotel"):
        if it.get("type") in ("hotel", "guest_house", "hostel", "apartment", "motel") and it.get("name"):
            tags = {**(it.get("extratags") or {}), "name": it["name"], "tourism": it["type"]}
            if (it.get("address") or {}).get("road"):
                tags["addr:street"] = it["address"]["road"]
            hotels.append({"type": it["osm_type"], "id": it["osm_id"], "tags": tags,
                           "pt": (float(it["lat"]), float(it["lon"]))})
    for it in _nominatim(dest, "restaurant"):
        if it.get("type") == "restaurant" and it.get("name"):
            ex = it.get("extratags") or {}
            restaurants.append({"name": it["name"], "cuisine": ex.get("cuisine", ""), "website": ex.get("website"),
                                "pt": (float(it["lat"]), float(it["lon"]))})
    return {"hotels": hotels, "beaches": [], "bars": [], "restaurants": restaurants,
            "source": "OpenStreetMap (Nominatim, reduced detail)", "reduced": True}


def area(dest: dict) -> dict:
    """Raw OSM data around the city centre. Overpass first (cached 14 days); Nominatim if it is down."""
    code = dest["code"]
    full = peek(f"osm_{code}", 14 * DAY)
    if full:
        return full
    # A recent fallback means Overpass was just down: reuse it instead of waiting on Overpass again.
    recent_fallback = peek(f"osmfb_{code}", 6 * 3600)
    if recent_fallback:
        return recent_fallback
    try:
        return cached(f"osm_{code}", 14 * DAY, lambda: _fetch_overpass(dest))
    except Exception:
        return cached(f"osmfb_{code}", 3 * DAY, lambda: _fetch_nominatim(dest))


def _stars(tags: dict) -> int | None:
    m = re.match(r"(\d)", str(tags.get("stars", "")))
    return int(m.group(1)) if m and 1 <= int(m.group(1)) <= 5 else None


def _amenities(tags: dict) -> list[str]:
    out = []
    if tags.get("internet_access") in ("wlan", "yes", "wifi") or tags.get("internet_access:fee") == "no":
        out.append("Wi-Fi")
    if tags.get("swimming_pool") == "yes" or tags.get("leisure") == "swimming_pool":
        out.append("Pool")
    if tags.get("air_conditioning") == "yes":
        out.append("Air conditioning")
    if tags.get("breakfast") == "yes":
        out.append("Breakfast")
    if tags.get("spa") == "yes" or tags.get("leisure") == "spa":
        out.append("Spa")
    if tags.get("wheelchair") == "yes":
        out.append("Step-free access")
    if tags.get("dog") == "yes" or tags.get("pets") == "yes":
        out.append("Pets welcome")
    if tags.get("parking") or tags.get("parking:fee"):
        out.append("Parking")
    return out


def interest_tags(dist_center_km: float, bars_n: int | None, food_n: int, beach_m: int | None, tags: dict) -> list[str]:
    """Interest tags derived from real OSM signals around the hotel (None = signal not available)."""
    out = []
    if beach_m is not None and beach_m <= 500:
        out.append("beachfront")
    if bars_n is not None and bars_n >= 6:
        out.append("nightlife")
    if food_n >= 10:
        out.append("food-scene")
    if dist_center_km <= 1.2:
        out.append("old-town")
    if tags.get("spa") == "yes" or tags.get("leisure") == "spa" or "spa" in tags.get("name", "").lower():
        out.append("spa")
    if dist_center_km > 1.5 and bars_n is not None and bars_n < 3:
        out.append("quiet")
    if tags.get("dog") == "yes" or tags.get("pets") == "yes":
        out.append("pet-friendly")
    return out


def signals_at(dest: dict, pt: tuple[float, float]) -> tuple[int | None, int, int | None]:
    """(bars within 300 m, restaurants within 300 m, metres to the nearest beach) around a point."""
    raw = area(dest)
    reduced = raw.get("reduced", False)
    bars = None if reduced else sum(1 for q in raw["bars"] if haversine_m(pt[0], pt[1], q[0], q[1]) <= 300)
    food = sum(1 for r in raw["restaurants"] if haversine_m(pt[0], pt[1], *r["pt"]) <= 300)
    beach = None if reduced else min((haversine_m(pt[0], pt[1], b[0], b[1]) for b in raw["beaches"]), default=None)
    return bars, food, beach


def real_hotels(dest: dict, limit: int = 8) -> list[dict]:
    """The most notable real hotels near the centre, WITHOUT prices."""
    raw = area(dest)
    reduced = raw.get("reduced", False)

    def notability(h):
        t = h["tags"]
        d = haversine_m(dest["lat"], dest["lng"], *h["pt"]) / 1000
        return ((_stars(t) or 0) + (2 if t.get("website") else 0) + (2 if t.get("wikidata") or t.get("wikipedia") else 0)
                + (1 if t.get("brand") else 0) + (1 if t.get("phone") else 0) + (1 if _amenities(t) else 0) - d * 0.3)

    seen, chosen = set(), []
    for h in sorted(raw["hotels"], key=notability, reverse=True):
        name = h["tags"]["name"].strip()
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        chosen.append(h)
        if len(chosen) == limit:
            break

    hotels = []
    for h in chosen:
        t, pt = h["tags"], h["pt"]
        dist = haversine_m(dest["lat"], dest["lng"], *pt) / 1000
        bars_n = None if reduced else sum(1 for q in raw["bars"] if haversine_m(pt[0], pt[1], q[0], q[1]) <= 300)
        food_n = sum(1 for r in raw["restaurants"] if haversine_m(pt[0], pt[1], *r["pt"]) <= 300)
        beach_m = None if reduced else min((haversine_m(pt[0], pt[1], b[0], b[1]) for b in raw["beaches"]), default=None)
        street = " ".join(x for x in (t.get("addr:street"), t.get("addr:housenumber")) if x)
        hotels.append({
            "id": f"osm-{h['type']}-{h['id']}",
            "name": t["name"],
            "destination": dest["code"],
            "kind": t.get("tourism", "hotel").replace("_", " "),
            "stars": _stars(t),
            "lat": round(pt[0], 5), "lng": round(pt[1], 5),
            "distance_to_center_km": round(dist, 1),
            "address": street or None,
            "website": t.get("website") or t.get("contact:website"),
            "osm_url": f"https://www.openstreetmap.org/{h['type']}/{h['id']}",
            "amenities": _amenities(t),
            "tags": interest_tags(dist, bars_n, food_n, beach_m, t),
            "signals": {
                "bars_300m": bars_n, "restaurants_300m": food_n,
                "beach_m": beach_m if beach_m is not None and beach_m < 3000 else None,
            },
        })
    return hotels


def nearby_restaurants(dest: dict, lat: float, lng: float, limit: int = 3, radius_m: int = 1200) -> list[dict]:
    """Real restaurants close to a point. No prices or discounts: OSM does not have them."""
    found = []
    for r in area(dest)["restaurants"]:
        d = haversine_m(lat, lng, *r["pt"])
        if d <= radius_m:
            cuisine = r["cuisine"].replace("_", " ").replace(";", ", ").capitalize() if r["cuisine"] else "Restaurant"
            found.append({
                "name": r["name"], "kind": "restaurant", "lat": r["pt"][0], "lng": r["pt"][1], "distance_m": d,
                "blurb": cuisine, "price": None, "rating": None, "deal": None, "website": r.get("website"),
            })
    return sorted(found, key=lambda v: v["distance_m"])[:limit]


# ---------------------------------------------------------------- places by type (museums, pubs, parks, ...)

# key -> (label, OSM tag, regex of accepted values, word for the Nominatim fallback)
PLACE_TYPES = {
    "museum": ("Museums", "tourism", "museum", "museum"),
    "gallery": ("Art galleries", "tourism", "gallery", "art gallery"),
    "pub": ("Pubs and bars", "amenity", "pub|bar", "pub"),
    "nightclub": ("Nightclubs", "amenity", "nightclub", "nightclub"),
    "park": ("Parks and gardens", "leisure", "park|garden", "park"),
    "viewpoint": ("Viewpoints", "tourism", "viewpoint", "viewpoint"),
    "market": ("Markets", "amenity", "marketplace", "market"),
    "historic": ("Historic sites", "historic", "castle|monument|memorial|archaeological_site|ruins|fort", "castle"),
    "theatre": ("Theatres and venues", "amenity", "theatre|arts_centre", "theatre"),
    "beach": ("Beaches", "natural", "beach", "beach"),
    "cafe": ("Cafes", "amenity", "cafe", "cafe"),
    "restaurant": ("Restaurants", "amenity", "restaurant", "restaurant"),
    "spa": ("Spas", "leisure", "spa|sauna", "spa"),
    "attraction": ("Family attractions", "tourism", "zoo|aquarium|theme_park", "zoo"),
}


def _type_of(tags: dict, wanted: list[str]) -> str | None:
    for key in wanted:
        _label, tag, values, _word = PLACE_TYPES[key]
        if re.fullmatch(values, tags.get(tag, "")):
            return key
    return None


def _place_record(dest: dict, e_type: str, e_id: int, tags: dict, pt, kind: str) -> dict:
    return {
        "id": f"osm-{e_type}-{e_id}", "type": kind, "name": tags["name"],
        "lat": round(pt[0], 5), "lng": round(pt[1], 5),
        "distance_to_center_km": round(haversine_m(dest["lat"], dest["lng"], *pt) / 1000, 1),
        "website": tags.get("website") or tags.get("contact:website"),
        "opening_hours": tags.get("opening_hours"),
        "wikipedia": tags.get("wikipedia"),
        "wikidata": tags.get("wikidata"),
        "osm_url": f"https://www.openstreetmap.org/{e_type}/{e_id}",
        "notable": bool(tags.get("wikipedia") or tags.get("wikidata")),
    }


def _fetch_types_overpass(dest: dict, wanted: list[str]) -> list[dict]:
    a = f"(around:{RADIUS},{dest['lat']},{dest['lng']})"
    parts = "".join(
        f'nwr["{PLACE_TYPES[k][1]}"~"^({PLACE_TYPES[k][2]})$"]["name"]{a};out center tags 60;' for k in wanted
    )
    out = []
    for e in _overpass(f"[out:json][timeout:22];{parts}")["elements"]:
        tags, pt = e.get("tags") or {}, _pt(e)
        kind = _type_of(tags, wanted) if tags.get("name") and pt else None
        if kind:
            out.append(_place_record(dest, e["type"], e["id"], tags, pt, kind))
    return out


def _fetch_types_nominatim(dest: dict, wanted: list[str]) -> list[dict]:
    out = []
    for key in wanted[:4]:  # be gentle with the public server
        for it in _nominatim(dest, PLACE_TYPES[key][3]):
            if it.get("name"):
                tags = {**(it.get("extratags") or {}), "name": it["name"]}
                out.append(_place_record(dest, it["osm_type"], it["osm_id"], tags, (float(it["lat"]), float(it["lon"])), key))
    return out


def places_of_type(dest: dict, types: list[str], per_type: int = 8) -> dict[str, list[dict]]:
    """Real places of the requested kinds around the city centre, most notable first. Types the traveler
    asked for that OSM has nothing for come back as empty lists. Opening hours are shown only when OSM has them."""
    wanted = [t for t in dict.fromkeys(types) if t in PLACE_TYPES]
    if not wanted:
        return {}
    key = f"osmtypes_{dest['code']}_{'-'.join(sorted(wanted))}"

    def fetch():
        try:
            return _fetch_types_overpass(dest, wanted)
        except Exception:
            found = _fetch_types_nominatim(dest, wanted)
            if not found:
                # The fallback found nothing: do not cache that for two weeks, try Overpass again next time.
                raise RuntimeError("no places of these types from the fallback")
            return found

    found = cached(key, 14 * DAY, fetch)
    grouped: dict[str, list[dict]] = {k: [] for k in wanted}
    seen = set()
    for p in sorted(found, key=lambda p: (not p["notable"], not p["website"], p["distance_to_center_km"])):
        if (p["type"], p["name"].lower()) in seen or len(grouped.get(p["type"], [])) >= per_type:
            continue
        seen.add((p["type"], p["name"].lower()))
        grouped[p["type"]].append(p)
    return grouped
