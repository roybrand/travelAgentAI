"""Real sights and photos from Wikipedia + Wikimedia Commons (free, no key).

Sights are Wikipedia articles near the city centre, ranked by their real page views over the last 30 days
(a good "how notable is this" signal) and kept only if they read like attractions and have a lead image.
Only photos under licences that allow reuse with credit (CC BY, CC BY-SA, CC0, public domain) are kept,
and author/licence travel with every photo so the UI can credit it.
"""
import math
import re

from app.live.http import DAY, cached, get_json

API = "https://en.wikipedia.org/w/api.php"

GOOD = re.compile(
    r"cathedral|basilica|church|abbey|monastery|palace|castle|fortress|\bfort\b|citadel|museum|gallery|square|piazza|"
    r"plaza|bridge|tower|\bgate\b|\barch\b|temple|shrine|mosque|synagogue|monument|memorial|market|theatre|theater|"
    r"opera|beach|viewpoint|\bpark\b|garden|waterfall|lake|island|ruins|amphitheat|colosseum|lighthouse|old town|"
    r"historic|district|quarter|promenade|boulevard|fountain|statue|\bzoo\b|aquarium|skyscraper|observation|pagoda|"
    r"cultural|landmark|tourist|heritage",
    re.I,
)
BAD = re.compile(
    r"railway|metro|subway|tram|bus |station|school|hospital|university|college|airport|company|corporation|bank\b|"
    r"prison|office|neighbou?rhood of|suburb|village in|municipality|band\b|album|film|television|circuit|racetrack|"
    r"race track|motorsport|cemetery|civil parish|freguesia|street in|road in|avenue in|highway|expressway",
    re.I,
)
# Lead images that are diagrams, maps or logos rather than photographs
BAD_IMAGE = re.compile(r"map|plan|diagram|logo|locator|coat.?of.?arms|flag|route|track|circuit|layout|\.svg", re.I)
OK_LICENSE = re.compile(r"^(CC BY(-SA)? [\d.]+|CC0|Public domain|PD)", re.I)
BAD_LICENSE = re.compile(r"NC|ND", re.I)

TAG_RULES = [
    ("beachfront", re.compile(r"\bbeach|\bcoast|seaside|\bbay\b|harbou?r|\bisland\b", re.I)),
    ("spa", re.compile(r"spa\b|thermal|hot spring|onsen|bath", re.I)),
    ("food-scene", re.compile(r"market|food|culinary|restaurant", re.I)),
    ("old-town", re.compile(r"old town|historic|quarter|district|medieval|square|piazza|plaza|cathedral|castle|palace|ruins", re.I)),
    ("nightlife", re.compile(r"nightlife|entertainment|nightclub|bar\b|opera|theat", re.I)),
    ("quiet", re.compile(r"\bpark\b|garden|lake|waterfall|nature|reserve|viewpoint", re.I)),
]


def _api(params: dict) -> dict:
    return get_json(API, {**params, "format": "json", "formatversion": 2}, timeout=30)


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def _norm(name: str) -> str:
    return name.replace("_", " ").removeprefix("File:").strip()


def credits_for(filenames: list[str]) -> dict[str, dict]:
    """Author + licence + source page for Commons files; keeps only reuse-with-credit licences."""
    names = sorted({_norm(f) for f in filenames if f})[:50]
    if not names:
        return {}
    data = _api({
        "action": "query", "titles": "|".join(f"File:{n}" for n in names),
        "prop": "imageinfo", "iiprop": "extmetadata|url",
    })
    out = {}
    for page in data.get("query", {}).get("pages", []):
        info = (page.get("imageinfo") or [None])[0]
        if not info:
            continue
        meta = info.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        if not OK_LICENSE.match(lic) or BAD_LICENSE.search(lic):
            continue
        out[_norm(page["title"])] = {
            "author": _strip_html(meta.get("Artist", {}).get("value", "")) or "Unknown",
            "license": lic,
            "license_url": meta.get("LicenseUrl", {}).get("value", ""),
            "source": info.get("descriptionurl", ""),
        }
    return out


def classify(text: str) -> list[str]:
    return [tag for tag, rx in TAG_RULES if rx.search(text)]


def _score(page: dict) -> float:
    """Notability: log of real 30-day page views, boosted when it reads like an attraction."""
    text = f"{page.get('title', '')} {page.get('description', '')}"
    if BAD.search(text) or not page.get("thumbnail") or BAD_IMAGE.search(page.get("pageimage", "")):
        return -1
    views = sum(v or 0 for v in (page.get("pageviews") or {}).values())
    return math.log10(1 + views) + (2.0 if GOOD.search(text) else 0.0)


def _candidates(dest: dict) -> list[dict]:
    """Up to 200 nearby articles around a city centre."""
    return _candidates_at(dest["lat"], dest["lng"], 7000)


def _candidates_at(lat: float, lng: float, radius_m: int) -> list[dict]:
    """Up to 200 articles around any point, with lead image, description and 30-day page views."""
    near = _api({
        "action": "query", "list": "geosearch", "gscoord": f"{lat}|{lng}",
        "gsradius": max(10, min(radius_m, 10000)), "gslimit": 200, "gsnamespace": 0,
    })["query"]["geosearch"]
    coords = {g["pageid"]: g for g in near}
    ids = list(coords)
    pages = []
    for i in range(0, len(ids), 50):
        batch = _api({
            "action": "query", "pageids": "|".join(map(str, ids[i:i + 50])),
            "prop": "pageimages|description|pageviews", "piprop": "thumbnail|name", "pithumbsize": 1000,
            "pilimit": 50, "pvipdays": 30,
        })
        for p in batch.get("query", {}).get("pages", []):
            g = coords.get(p["pageid"], {})
            p["coordinates"] = [{"lat": g.get("lat"), "lon": g.get("lon")}]
            pages.append(p)
    return pages


def _fetch(dest: dict, limit: int) -> dict:
    ranked = sorted(_candidates(dest), key=_score, reverse=True)
    pages = [p for p in ranked if _score(p) >= 2.5][:limit] or [p for p in ranked if _score(p) >= 0][:limit]

    extracts = {}
    if pages:
        ex = _api({
            "action": "query", "pageids": "|".join(str(p["pageid"]) for p in pages[:20]),
            "prop": "extracts", "exintro": 1, "explaintext": 1, "exsentences": 2, "exlimit": 20,
        })
        extracts = {p["pageid"]: p.get("extract", "") for p in ex.get("query", {}).get("pages", [])}
    for p in pages:
        p["extract"] = extracts.get(p["pageid"], "")

    hero_data = _api({
        "action": "query", "titles": dest["wiki"], "redirects": 1,
        "prop": "pageimages|description", "piprop": "thumbnail|name", "pithumbsize": 1600,
    })
    hero_page = (hero_data.get("query", {}).get("pages") or [{}])[0]

    files = [p.get("pageimage") for p in pages] + [hero_page.get("pageimage")]
    creds = credits_for([f for f in files if f])

    places = []
    for p in pages:
        coords = (p.get("coordinates") or [{}])[0]
        text = f"{p.get('title', '')} {p.get('description', '')} {p.get('extract', '')}"
        cred = creds.get(_norm(p.get("pageimage", "")))
        places.append({
            "name": p["title"],
            "why": p.get("description") or (p.get("extract", "").split(". ")[0] + "."),
            "extract": p.get("extract", ""),
            "photo_url": p["thumbnail"]["source"] if cred else None,
            "photo_credit": cred,
            "lat": coords.get("lat"), "lng": coords.get("lon"),
            "url": f"https://en.wikipedia.org/?curid={p['pageid']}",
            "views_30d": sum(v or 0 for v in (p.get("pageviews") or {}).values()),
            "tags": classify(text),
        })

    hero = None
    hcred = creds.get(_norm(hero_page.get("pageimage", "")))
    if hero_page.get("thumbnail") and hcred:
        hero = {"url": hero_page["thumbnail"]["source"], "credit": hcred}
    return {"hero": hero, "places": places}


def sights(dest: dict, limit: int = 8) -> dict:
    """{"hero": {url, credit} | None, "places": [...]} for a catalog destination (cached 30 days)."""
    return cached(f"places_{dest['code']}", 30 * DAY, lambda: _fetch(dest, limit))
