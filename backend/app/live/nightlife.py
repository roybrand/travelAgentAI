"""Tonight: the best clubs and bars in a city for one evening, with photos, opening hours and real prices.

What the free sources can and cannot tell us:
- OpenStreetMap gives real venues, opening hours (often), websites and a "notable" signal (a Wikipedia entry).
- Wikimedia Commons gives credited photos for venues that have one.
- Prices exist only when a venue posts a partner deal (our own database) or an event is listed on Ticketmaster.
  Nothing is estimated or invented: a venue with no published price says so.
- There are no guest reviews in any free source, so "best" here means best documented and open that night,
  nearest the centre, with a live deal or event as a bonus. The response says this in `ranking_note`.
"""
import math
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from app.live import catalog, osm
from app.live.geo import haversine_m
from app.live.http import DAY, cached, get_json
from app.live.places import BAD_IMAGE, BAD_LICENSE, OK_LICENSE, _strip_html

KINDS = {"clubs": ("nightclub", "Nightclub"), "bars": ("pub", "Bar or pub")}
COMMONS = "https://commons.wikimedia.org/w/api.php"
RANKING_NOTE = (
    "Free sources have no guest reviews and no ticket prices, so venues are ranked by how well documented they are, "
    "whether they are open that night, how close they are to the centre, and any live deal or event. "
    "A price appears only when the venue or Ticketmaster publishes one."
)
NO_PRICE = "No price published. Ask the venue."
NIGHT_START, NIGHT_END = 20 * 60, 30 * 60  # "tonight" runs from 20:00 to 06:00 the next morning, in minutes

# ---------------------------------------------------------------- opening hours

_DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
_TIMES = re.compile(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$")


def _day_set(spec: str) -> set[int] | None:
    out = set()
    for part in spec.replace(" ", "").split(","):
        if part in ("PH", "SH", ""):
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            if a not in _DAYS or b not in _DAYS:
                return None
            i, j = _DAYS.index(a), _DAYS.index(b)
            out |= set(range(i, j + 1)) if i <= j else set(range(i, 7)) | set(range(0, j + 1))
        elif part in _DAYS:
            out.add(_DAYS.index(part))
        else:
            return None
    return out


def _ranges(spec: str) -> list[tuple[int, int]] | None:
    spec = spec.strip()
    if spec.lower() in ("off", "closed"):
        return []
    out = []
    for part in spec.split(","):
        m = _TIMES.match(part.strip())
        if not m:
            return None
        h1, m1, h2, m2 = map(int, m.groups())
        out.append((h1 * 60 + m1, h2 * 60 + m2))
    return out


def parse_hours(oh: str | None) -> dict[int, list[tuple[int, int]]] | None:
    """A weekday -> opening ranges map for the common OpenStreetMap patterns, or None if it cannot be read.
    Later rules override earlier ones, as in OpenStreetMap. Public-holiday rules are ignored."""
    if not oh or not oh.strip():
        return None
    week: dict[int, list[tuple[int, int]]] = {}
    for rule in (r.strip() for r in oh.split(";")):
        if not rule:
            continue
        if rule == "24/7":
            week = {d: [(0, 1440)] for d in range(7)}
            continue
        head, _, tail = rule.rpartition(" ")
        days = _day_set(head) if head else set(range(7))
        ranges = _ranges(tail if head else rule)
        if days is None or ranges is None:
            return None
        for d in days:
            week[d] = ranges
    return week


def _clock(minutes: int) -> str:
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


def tonight(oh: str | None, day: date) -> dict:
    """Is it open at some point between 20:00 on `day` and 06:00 the next morning?
    `open` is True, False, or None when the hours are missing or not understood."""
    week = parse_hours(oh)
    if week is None:
        return {"open": None, "hours": None}
    for start, end in week.get(day.weekday(), []):
        if end <= start:
            end += 1440  # runs past midnight
        if start < NIGHT_END and end > NIGHT_START:
            return {"open": True, "hours": f"{_clock(start)}–{_clock(end)}", "late": end > 1440 + 30}
    return {"open": False, "hours": None}


# ---------------------------------------------------------------- photos (Wikimedia Commons)

_GENERIC = {"the", "and", "club", "bar", "pub", "cafe", "lounge", "disco", "discoteca", "nightclub", "restaurant", "de", "la", "el", "los", "las", "o", "a"}


def _tokens(text: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z0-9]{3,}", plain)


def matches_name(title: str, name: str) -> bool:
    """A Commons file title counts as this venue only if it carries the venue's distinctive name words."""
    want = [t for t in _tokens(name) if t not in _GENERIC]
    if not want:
        return False
    have = set(_tokens(title))
    hit = sum(t in have for t in want)
    return hit == len(want) if len(want) <= 2 else hit >= math.ceil(len(want) / 2)


def pick_photo(pages: list[dict], name: str) -> dict | None:
    """The first credited, reusable photograph whose title matches the venue name."""
    for page in sorted(pages, key=lambda p: p.get("index", 0)):
        title = page.get("title", "")
        info = (page.get("imageinfo") or [None])[0]
        if not info or BAD_IMAGE.search(title) or not matches_name(title.removeprefix("File:"), name):
            continue
        meta = info.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        if not OK_LICENSE.match(lic) or BAD_LICENSE.search(lic) or not info.get("thumburl"):
            continue
        return {
            "url": info["thumburl"],
            "credit": {
                "author": _strip_html(meta.get("Artist", {}).get("value", "")) or "Unknown", "license": lic,
                "license_url": meta.get("LicenseUrl", {}).get("value", ""), "source": info.get("descriptionurl", ""),
            },
        }
    return None


def venue_photo(name: str, city: str) -> dict | None:
    def fetch():
        data = get_json(COMMONS, {
            "action": "query", "format": "json", "formatversion": 2, "generator": "search",
            "gsrsearch": f"{name} {city}", "gsrnamespace": 6, "gsrlimit": 4,
            "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 640,
        }, timeout=20)
        return pick_photo(data.get("query", {}).get("pages", []), name)

    slug = re.sub(r"[^a-z0-9]+", "-", f"{name}-{city}".lower())[:80]
    return cached(f"nlphoto_{slug}", 30 * DAY, fetch)


# ---------------------------------------------------------------- ranking

def rank_venues(places: list[dict], day: date, deals: list[dict] = ()) -> tuple[list[dict], int]:
    """Score real venues for one night. Returns (ranked venues, number hidden because they are closed that night)."""
    out, closed = [], 0
    owner = _deal_owners(places, deals)
    for p in places:
        night = tonight(p.get("opening_hours"), day)
        if night["open"] is False:
            closed += 1
            continue
        score, why = 0.0, []
        if night["open"]:
            score += 1.5
            why.append(f"Open tonight {night['hours']}")
            if night["late"]:
                score += 0.7
                why.append("Open past midnight")
        else:
            why.append("Opening hours not listed. Check before you go")
        if p["type"] == "nightclub":
            score += 0.5
        if p.get("notable"):
            score += 2.0
            why.append("Well documented (has a Wikipedia entry)")
        if p.get("website"):
            score += 0.5
        score -= 0.15 * p.get("distance_to_center_km", 0)
        near = [d for d in deals if owner.get(d["id"]) == p["id"]]
        if near:
            score += 1.0
            why.append("Has a partner deal tonight")
        out.append({**p, "kind_label": KINDS_BY_TYPE.get(p["type"], "Venue"), "tonight": night, "why": why,
                    "score": round(score, 3), "deal": near[0] if near else None})
    out.sort(key=lambda v: (-v["score"], v["name"]))
    return out, closed


KINDS_BY_TYPE = {t: label for t, label in KINDS.values()}
DEAL_RADIUS_M = 100


def _deal_owners(places: list[dict], deals: list[dict]) -> dict[int, str]:
    """Each deal belongs to at most one venue: the nearest one within 100 m. Several bars can share a street,
    and a deal must never be shown against a venue it is not for."""
    owner = {}
    for d in deals:
        if d.get("lat") is None or not places:
            continue
        best = min(places, key=lambda p: haversine_m(p["lat"], p["lng"], d["lat"], d["lng"]))
        if haversine_m(best["lat"], best["lng"], d["lat"], d["lng"]) <= DEAL_RADIUS_M:
            owner[d["id"]] = best["id"]
    return owner


def _events_tonight(events: list[dict], day: date) -> list[dict]:
    keep = [e for e in events if e.get("date") == day.isoformat()]
    return sorted(keep, key=lambda e: e.get("time") or "99:99")


def build(dest: dict, day: date, places: list[dict], deals: list[dict], events: list[dict], photo_fn=None, limit: int = 12) -> dict:
    """Assemble the Tonight response from already-fetched data. `photo_fn(name, city)` is injected so tests need no network."""
    ranked, closed = rank_venues(places, day, deals)
    top = ranked[:limit]
    if photo_fn and top:
        with ThreadPoolExecutor(max_workers=5) as pool:
            photos = list(pool.map(lambda v: _safe(photo_fn, v["name"], dest["city"]), top))
        for v, ph in zip(top, photos):
            v["photo_url"], v["photo_credit"] = (ph["url"], ph["credit"]) if ph else (None, None)
            v["score"] = round(v["score"] + (0.5 if ph else 0), 3)
        top.sort(key=lambda v: (-v["score"], v["name"]))
    for v in top:
        v.setdefault("photo_url", None)
        v.setdefault("photo_credit", None)
        v["price"] = v["deal"]["price"] if v["deal"] else None
        v["price_note"] = None if v["deal"] else NO_PRICE
    used = {v["deal"]["id"] for v in top if v["deal"]}
    return {
        "date": day.isoformat(), "city": dest["city"], "dest": dest["code"], "venues": top,
        "closed_hidden": closed, "deals": [d for d in deals if d["id"] not in used], "events": _events_tonight(events, day),
        "ranking_note": RANKING_NOTE,
    }


def _safe(fn, *args):
    try:
        return fn(*args)
    except Exception:
        return None  # a missing photo must never fail the page


# ---------------------------------------------------------------- orchestration

def run(dest_code: str, day: date, kinds: list[str]) -> dict:
    """Live lookup: OpenStreetMap venues, Commons photos, partner deals, and Ticketmaster events if a key is set."""
    from app.partners import deals as partner_deals
    from app.suppliers import ticketmaster

    dest = catalog.BY_CODE[dest_code]
    types = [KINDS[k][0] for k in kinds if k in KINDS]
    notes = []
    grouped = osm.places_of_type(dest, types, per_type=30) if types else {}
    places = [p for group in grouped.values() for p in group]
    if types and not places:
        notes.append("No venues found in OpenStreetMap for this city yet. Deals and events below may still help.")
    deals = partner_deals.rank_deals(
        [d for d in partner_deals.for_city(dest_code, day, day) if d["category"] in ("party", "bar")], ["nightlife"], ["nightclub", "pub"])
    events = []
    if ticketmaster.enabled():
        try:
            events = ticketmaster.events_for_trip(dest["lat"], dest["lng"], day, day, radius_km=20)
        except Exception:
            notes.append("Live events are temporarily unavailable.")
    result = build(dest, day, places, deals, events, photo_fn=venue_photo)
    partner_deals.record_impressions([d["id"] for d in result["deals"]] + [v["deal"]["id"] for v in result["venues"] if v["deal"]])
    result["notes"] = notes
    result["events_enabled"] = ticketmaster.enabled()
    return result


def run_local(dest_code: str, day: date) -> dict:
    """Offline mode: no internet lookups, but partner deals for the night still show."""
    from app.partners import deals as partner_deals

    dest = catalog.BY_CODE[dest_code]
    deals = partner_deals.rank_deals(
        [d for d in partner_deals.for_city(dest_code, day, day) if d["category"] in ("party", "bar")], ["nightlife"], ["nightclub", "pub"])
    result = build(dest, day, [], deals, [])
    result["notes"] = ["Offline mode: venue lookups need internet. Partner deals are still shown."]
    result["events_enabled"] = False
    return result


def valid_day(day: date | None) -> date:
    today = date.today()
    day = day or today
    if not today <= day <= today + timedelta(days=14):
        raise ValueError("Choose a night from today to two weeks ahead.")
    return day
