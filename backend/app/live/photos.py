"""Find a real, credited photo for a named place or activity (Wikipedia, Wikidata, Wikimedia Commons; free, no key).

Used for guide items that arrive without a photo: curated activities ("Float in the Dead Sea"), OpenStreetMap places
(beaches, zoos, parks) and Wikipedia sights whose own lead image is not reusable. Tried in order, most exact first:

1. the place's own Wikipedia article or Wikidata item, when OpenStreetMap links one (exact match);
2. a Wikipedia search for the name, accepted only when the article title shares a real word with the name;
3. for outdoor spots (beaches, viewpoints, parks), Commons photos taken within a few hundred metres whose file name
   says what they show (beach, sea, sunset, ...); tried before the name searches, since a location is exact;
4. a search of Commons photos for the name, accepted only when the file name contains its proper name ("Tagus"), or
   for a generic activity both a key word and the city ("Dubai desert safari").

Curated activities can carry a `photo_query` (e.g. "Dead Sea") when their name describes an activity, not a place.

Only licences that allow reuse with credit are kept (same rule as the sights), and author/licence travel with the
photo. Each lookup is cached for 30 days, including "nothing found", so a city is searched once. A lookup that hit an
error is not cached, so a temporary outage never hides a photo for a month.
"""
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor, wait

from app.config import offline
from app.live.http import DAY, cached, get_json
from app.live.places import BAD_IMAGE, BAD_LICENSE, OK_LICENSE, _strip_html

COMMONS = "https://commons.wikimedia.org/w/api.php"
WIKIDATA = "https://www.wikidata.org/w/api.php"
WIDTH = 1000

# Words that describe the activity rather than the place, so they cannot prove a search hit is the right place.
STOP = {
    "and", "the", "with", "from", "along", "into", "near", "over", "day", "trip", "tour", "walk", "night", "float",
    "evening", "morning", "sunset", "sunrise", "visit", "local", "best", "classic", "city", "view", "views", "sail",
    "drive", "ride", "street", "food", "dinner", "lunch", "drinks", "bar", "bars", "club", "shared",
}
# Words dropped before searching Commons, whose search needs every word to match.
FILLER = {"and", "the", "with", "from", "along", "into", "walk", "trip", "day", "float", "visit", "tour", "shared", "in",
          "on", "at", "to", "of", "a"}
# For outdoor spots, a nearby Commons photo counts only when its file name says it shows this kind of place.
NEARBY_HINTS = {
    "beach": re.compile(r"beach|coast|shore|\bsea\b|sunset|seaside|promenade|plage|praia|playa|spiaggia|strand|חוף", re.I),
    "viewpoint": re.compile(r"view|panorama|skyline|sunset|lookout|overlook|mirador|miradouro", re.I),
    "park": re.compile(r"park|garden|gan|jardin|jardim|giardino|tree|lake|pond|פארק|גן", re.I),
}

# Nearby photos of an event rather than the place itself.
EVENT = re.compile(r"protest|demonstrat|rally|parade|march|portrait|selfie|wedding|conference|meeting|ceremony|funeral", re.I)


def _words(text: str, city: str = "") -> set[str]:
    skip = STOP | {w.lower() for w in re.findall(r"\w+", city)}
    return {w for w in re.findall(r"\w+", text.lower()) if len(w) >= 4 and w not in skip}


def _file_photos(filenames: list[str]) -> dict[str, dict]:
    """{file name: {url, credit}} for Commons files whose licence allows reuse with credit."""
    names = [f.removeprefix("File:").replace("_", " ").strip() for f in filenames if f][:20]
    names = [n for n in names if not BAD_IMAGE.search(n)]
    if not names:
        return {}
    data = get_json(COMMONS, {
        "action": "query", "titles": "|".join(f"File:{n}" for n in names), "prop": "imageinfo",
        "iiprop": "extmetadata|url", "iiurlwidth": WIDTH, "format": "json", "formatversion": 2,
    }, timeout=20)
    out = {}
    for page in data.get("query", {}).get("pages", []):
        info = (page.get("imageinfo") or [None])[0]
        if not info:
            continue
        meta = info.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        if not OK_LICENSE.match(lic) or BAD_LICENSE.search(lic):
            continue
        out[page["title"].removeprefix("File:")] = {
            "url": info.get("thumburl") or info.get("url"),
            "credit": {
                "author": _strip_html(meta.get("Artist", {}).get("value", "")) or "Unknown",
                "license": lic,
                "license_url": meta.get("LicenseUrl", {}).get("value", ""),
                "source": info.get("descriptionurl", ""),
            },
        }
    return out


def _first_photo(filenames: list[str]) -> dict | None:
    found = _file_photos(filenames)
    for f in filenames:
        hit = found.get(f.removeprefix("File:").replace("_", " ").strip())
        if hit:
            return hit
    return None


def _article_image(lang: str, title: str) -> str | None:
    data = get_json(f"https://{lang}.wikipedia.org/w/api.php", {
        "action": "query", "titles": title, "redirects": 1, "prop": "pageimages", "piprop": "name",
        "format": "json", "formatversion": 2,
    }, timeout=20)
    return ((data.get("query", {}).get("pages") or [{}])[0]).get("pageimage")


def _from_wikipedia_tag(tag: str) -> dict | None:
    """OpenStreetMap's `wikipedia` tag looks like "en:Ramat Gan Safari"."""
    lang, _, title = tag.partition(":")
    if not title or not re.fullmatch(r"[a-z-]{2,12}", lang):
        return None
    image = _article_image(lang, title)
    return _first_photo([image]) if image else None


def _from_wikidata(qid: str) -> dict | None:
    if not re.fullmatch(r"Q\d+", qid or ""):
        return None
    data = get_json(WIKIDATA, {"action": "wbgetentities", "ids": qid, "props": "claims", "format": "json"}, timeout=20)
    claims = data.get("entities", {}).get(qid, {}).get("claims", {})
    files = [c["mainsnak"]["datavalue"]["value"] for c in claims.get("P18", []) if c.get("mainsnak", {}).get("datavalue")]
    return _first_photo(files) if files else None


def _from_search(query: str, must: set[str]) -> dict | None:
    """The top Wikipedia search hits with an image, accepted only when the title shares a real word with the name."""
    if not must:
        return None
    data = get_json("https://en.wikipedia.org/w/api.php", {
        "action": "query", "generator": "search", "gsrsearch": query, "gsrlimit": 5, "gsrnamespace": 0,
        "prop": "pageimages", "piprop": "name", "format": "json", "formatversion": 2,
    }, timeout=20)
    pages = sorted(data.get("query", {}).get("pages", []), key=lambda p: p.get("index", 99))
    files = [p["pageimage"] for p in pages if p.get("pageimage") and must & _words(p.get("title", ""))]
    return _first_photo(files) if files else None


def _from_commons_search(query: str, city: str, need_city: bool) -> dict | None:
    """Commons photos matching the name. A proper name in it ("the Tagus") is specific enough on its own; a generic
    activity ("Desert safari") must also match the city, unless the query was written for this item."""
    city_words = {w.lower() for w in re.findall(r"\w+", city)}
    words = [w for w in re.findall(r"\w+", query) if w.lower() not in FILLER]
    content = {w.lower() for w in words if len(w) >= 4} - city_words
    if not content:
        return None
    proper = {w.lower() for w in words[1:] if w[0].isupper() and len(w) >= 4} - city_words
    need_city = need_city and not proper
    # Commons needs every word to match, so if the whole name finds nothing, retry with the proper name plus one
    # other word at a time ("Tagus sunset", "Tagus sail"), then the proper name alone.
    texts = [" ".join(words) + ("" if not need_city or city.lower() in query.lower() else f" {city}")]
    if proper:
        name = " ".join(w for w in words if w.lower() in proper)
        texts += [f"{name} {w}" for w in words if len(w) >= 4 and w.lower() not in proper][:2] + [name]
    # Words that name the thing ("promenade", "tagus") must show up; "sunset" alone proves nothing.
    key_words = proper or (content - STOP) or content
    city_rx = re.compile(re.escape(city.split()[0]), re.I)
    for text in texts:
        data = get_json(COMMONS, {
            "action": "query", "list": "search", "srsearch": f"{text} filetype:bitmap", "srnamespace": 6, "srlimit": 10,
            "format": "json", "formatversion": 2,
        }, timeout=20)
        files = [h["title"] for h in data.get("query", {}).get("search", [])
                 if any(w in h["title"].lower() for w in key_words) and (not need_city or city_rx.search(h["title"]))]
        hit = _first_photo(files[:8]) if files else None
        if hit:
            return hit
    return None


def _from_nearby(lat: float, lng: float, hint: re.Pattern) -> dict | None:
    data = get_json(COMMONS, {
        "action": "query", "list": "geosearch", "gscoord": f"{lat}|{lng}", "gsradius": 400, "gsnamespace": 6,
        "gslimit": 40, "format": "json", "formatversion": 2,
    }, timeout=20)
    files = [g["title"] for g in data.get("query", {}).get("geosearch", []) if hint.search(g["title"]) and not EVENT.search(g["title"])]
    files = [f for f in files if re.search(r"\.(jpe?g|png|webp)$", f, re.I)][:10]
    return _first_photo(files) if files else None


def find_photo(item: dict, city: str) -> dict | None:
    """{"url", "credit"} for one guide item, or None. Never raises; cached (including misses) for 30 days."""
    if offline():
        return None
    name = item.get("name", "")
    query = item.get("photo_query") or name
    kind = item.get("type") or ""
    ident = "|".join(str(item.get(k) or "") for k in ("wikipedia", "wikidata", "lat", "lng")) + f"|{query}|{kind}|{city}"
    key = "photo_" + hashlib.sha1(ident.encode("utf-8")).hexdigest()[:20]

    def fetch():
        failed = None
        for attempt in (
            lambda: item.get("wikipedia") and _from_wikipedia_tag(item["wikipedia"]),
            lambda: item.get("wikidata") and _from_wikidata(item["wikidata"]),
            # A photo taken at the spot beats a name search for outdoor places, whose names are often generic.
            lambda: kind in NEARBY_HINTS and item.get("lat") is not None and _from_nearby(item["lat"], item["lng"], NEARBY_HINTS[kind]),
            lambda: _from_search(query if item.get("photo_query") else f"{query} {city}", _words(query, city)),
            lambda: _from_commons_search(query, city, need_city=not item.get("photo_query")),
        ):
            try:
                hit = attempt()
            except Exception as exc:
                hit, failed = None, exc
            if hit:
                return hit
        if failed:
            raise failed  # not cached: try again next time
        return {"none": True}

    try:
        found = cached(key, 30 * DAY, fetch)
    except Exception:
        return None
    return None if not found or found.get("none") else found


def fill(items: list[dict], city: str, budget_s: float = 12.0) -> None:
    """Give every item that has no photo yet a real one where one can be found, in place and in parallel.
    Lookups still running after `budget_s` finish in the background and are cached for the next search."""
    todo = [i for i in items if not i.get("photo") and not i.get("photo_url")]
    if not todo or offline():
        return
    pool = ThreadPoolExecutor(max_workers=8)
    futures = {pool.submit(find_photo, i, city): i for i in todo}
    done, _ = wait(futures, timeout=budget_s)
    pool.shutdown(wait=False)
    for f in done:
        hit = f.result()
        if hit:
            futures[f]["photo_url"] = hit["url"]
            futures[f]["photo_credit"] = hit["credit"]
