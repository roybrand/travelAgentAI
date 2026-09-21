"""Live destination guide for catalog cities.

Real: monthly climate (Open-Meteo), sights + photos (Wikipedia/Wikimedia), restaurants (OpenStreetMap).
Curated: for showcase cities, the hand-written highlights (with typical costs) are kept, but their
FICTIONAL demo venues and discounts are dropped and replaced by real nearby restaurants without prices.
"""
from datetime import date

from app.live import catalog, climate, osm, places
from app.mcp_tools.guides_data import assess_timing, build_guide

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
               "October", "November", "December"]
# Curated tags from the earlier demo vocabulary, mapped onto the live interest keys
ALIASES = {"michelin-nearby": "food-scene", "rooftop-bar": "nightlife"}


def _matches(tags: list[str], interests: list[str]) -> list[str]:
    return sorted({ALIASES.get(t, t) for t in tags} & set(interests))


def _venues(dest: dict, items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for item in items:
        for v in item.get("nearby", []):
            if v["name"] not in seen:
                seen.add(v["name"])
                out.append(v)
    return out


def build_live_guide(dest: dict, start_date: str, end_date: str, interests: list[str], place_types: list[str] | None = None) -> dict:
    base = build_guide(dest["code"], start_date, end_date, interests)  # curated content, if any
    clim = climate.monthly_climate(dest)
    timing = assess_timing(clim["scores"], date.fromisoformat(start_date), date.fromisoformat(end_date))

    try:
        wiki = places.sights(dest)
    except Exception:
        wiki = {"hero": None, "places": []}
    try:
        osm.area(dest)
        dining = True
    except Exception:
        dining = False

    def with_dining(item: dict) -> dict:
        item = {**item, "matches": _matches(item.get("tags", []), interests)}
        item.pop("nearby", None)
        if dining and item.get("lat") is not None:
            item["nearby"] = osm.nearby_restaurants(dest, item["lat"], item["lng"])
        else:
            item["nearby"] = []
        return item

    if base.get("rich"):
        place_items = [with_dining(p) for p in base["places"]]
        adventure_items = [with_dining(a) for a in base["adventures"]]
        hero, hero_url, hero_credit = base["hero"], None, None
    else:
        place_items = [with_dining({**p, "photo": None}) for p in wiki["places"]]
        adventure_items = [{**a, "matches": _matches(a.get("tags", []), interests), "nearby": []} for a in base.get("adventures", [])]
        hero = None
        hero_url = wiki["hero"]["url"] if wiki["hero"] else None
        hero_credit = wiki["hero"]["credit"] if wiki["hero"] else None

    by_type = {}
    if place_types:
        try:
            for kind, found in osm.places_of_type(dest, place_types).items():
                by_type[kind] = {"label": osm.PLACE_TYPES[kind][0], "places": found}
        except Exception:
            by_type = {}

    place_items.sort(key=lambda i: -len(i["matches"]))
    adventure_items.sort(key=lambda i: -len(i["matches"]))
    names = MONTH_NAMES
    return {
        "found": True, "source": "live", "rich": bool(base.get("rich")),
        "name": f"{dest['city']}, {dest['country']}",
        "center": [dest["lat"], dest["lng"]],
        "hero": hero, "hero_url": hero_url, "hero_credit": hero_credit,
        "months": clim["scores"], "climate": clim["months"], "climate_source": clim["source"],
        "season_note": climate.season_note(clim, names),
        "timing": timing,
        "places": place_items, "adventures": adventure_items,
        "venues": _venues(dest, place_items + adventure_items),
        "by_type": by_type,
        "tips": base.get("tips", []),
        "sources": {
            "climate": clim["source"],
            "sights": "Wikipedia (ranked by page views)" if not base.get("rich") else "Curated highlights",
            "dining": "OpenStreetMap restaurants" if dining else None,
        },
    }
