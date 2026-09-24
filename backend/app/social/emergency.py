"""Local emergency numbers for every country in the destination catalog, shown next to the safety tools.

The country comes from the catalog, not a map service: the nearest catalog city to a position (within
NEAR_KM), a catalog city code, or a country name. No network call, so it works offline and never sends a
location anywhere. The numbers are the widely published ones as of VERIFIED, not yet checked one by one
against each government's own page -- do that before launch (docs/PRODUCTION_CHECKLIST.md). The app always
tells people to confirm locally, because numbers do change.
"""
import math

from app.live import catalog

VERIFIED = "2026-09"
NEAR_KM = 400  # further than this from every catalog city, we don't guess a country

# general: the one number that reaches every service (None if the country has no single number).
# police / ambulance / fire: the direct lines. tourist: a tourist police line, where one exists.
NUMBERS: dict[str, dict] = {
    "Argentina": {"general": "911", "police": "911", "ambulance": "107", "fire": "100"},
    "Australia": {"general": "000", "police": "000", "ambulance": "000", "fire": "000"},
    "Austria": {"general": "112", "police": "133", "ambulance": "144", "fire": "122"},
    "Belgium": {"general": "112", "police": "101", "ambulance": "112", "fire": "112"},
    "Brazil": {"general": None, "police": "190", "ambulance": "192", "fire": "193"},
    "Cambodia": {"general": None, "police": "117", "ambulance": "119", "fire": "118"},
    "Canada": {"general": "911", "police": "911", "ambulance": "911", "fire": "911"},
    "Chile": {"general": None, "police": "133", "ambulance": "131", "fire": "132"},
    "China": {"general": None, "police": "110", "ambulance": "120", "fire": "119"},
    "Colombia": {"general": "123", "police": "123", "ambulance": "123", "fire": "123"},
    "Costa Rica": {"general": "911", "police": "911", "ambulance": "911", "fire": "911"},
    "Croatia": {"general": "112", "police": "192", "ambulance": "194", "fire": "193"},
    "Cuba": {"general": None, "police": "106", "ambulance": "104", "fire": "105"},
    "Czechia": {"general": "112", "police": "158", "ambulance": "155", "fire": "150"},
    "Denmark": {"general": "112", "police": "112", "ambulance": "112", "fire": "112"},
    "Ecuador": {"general": "911", "police": "911", "ambulance": "911", "fire": "911"},
    "Estonia": {"general": "112", "police": "112", "ambulance": "112", "fire": "112"},
    "Finland": {"general": "112", "police": "112", "ambulance": "112", "fire": "112"},
    "France": {"general": "112", "police": "17", "ambulance": "15", "fire": "18"},
    "Germany": {"general": "112", "police": "110", "ambulance": "112", "fire": "112"},
    "Greece": {"general": "112", "police": "100", "ambulance": "166", "fire": "199", "tourist": "1571"},
    "Hungary": {"general": "112", "police": "107", "ambulance": "104", "fire": "105"},
    "Iceland": {"general": "112", "police": "112", "ambulance": "112", "fire": "112"},
    "India": {"general": "112", "police": "100", "ambulance": "108", "fire": "101"},
    "Indonesia": {"general": "112", "police": "110", "ambulance": "118", "fire": "113"},
    "Ireland": {"general": "112", "police": "112", "ambulance": "112", "fire": "112"},
    "Israel": {"general": None, "police": "100", "ambulance": "101", "fire": "102"},
    "Italy": {"general": "112", "police": "113", "ambulance": "118", "fire": "115"},
    "Japan": {"general": None, "police": "110", "ambulance": "119", "fire": "119"},
    "Jordan": {"general": "911", "police": "911", "ambulance": "911", "fire": "911"},
    "Malaysia": {"general": "999", "police": "999", "ambulance": "999", "fire": "994"},
    "Maldives": {"general": None, "police": "119", "ambulance": "102", "fire": "118"},
    "Malta": {"general": "112", "police": "112", "ambulance": "112", "fire": "112"},
    "Mexico": {"general": "911", "police": "911", "ambulance": "911", "fire": "911"},
    "Netherlands": {"general": "112", "police": "112", "ambulance": "112", "fire": "112"},
    "Norway": {"general": None, "police": "112", "ambulance": "113", "fire": "110"},
    "Panama": {"general": "911", "police": "104", "ambulance": "911", "fire": "103"},
    "Peru": {"general": None, "police": "105", "ambulance": "106", "fire": "116"},
    "Philippines": {"general": "911", "police": "911", "ambulance": "911", "fire": "911"},
    "Poland": {"general": "112", "police": "997", "ambulance": "999", "fire": "998"},
    "Portugal": {"general": "112", "police": "112", "ambulance": "112", "fire": "112"},
    "Puerto Rico": {"general": "911", "police": "911", "ambulance": "911", "fire": "911"},
    "Qatar": {"general": "999", "police": "999", "ambulance": "999", "fire": "999"},
    "Serbia": {"general": None, "police": "192", "ambulance": "194", "fire": "193"},
    "Singapore": {"general": None, "police": "999", "ambulance": "995", "fire": "995"},
    "South Korea": {"general": None, "police": "112", "ambulance": "119", "fire": "119"},
    "Spain": {"general": "112", "police": "091", "ambulance": "112", "fire": "112"},
    "Sri Lanka": {"general": None, "police": "119", "ambulance": "1990", "fire": "110"},
    "Sweden": {"general": "112", "police": "112", "ambulance": "112", "fire": "112"},
    "Switzerland": {"general": "112", "police": "117", "ambulance": "144", "fire": "118"},
    "Taiwan": {"general": None, "police": "110", "ambulance": "119", "fire": "119"},
    "Thailand": {"general": None, "police": "191", "ambulance": "1669", "fire": "199", "tourist": "1155"},
    "Turkey": {"general": "112", "police": "112", "ambulance": "112", "fire": "112"},
    "United Arab Emirates": {"general": None, "police": "999", "ambulance": "998", "fire": "997"},
    "United Kingdom": {"general": "999", "police": "999", "ambulance": "999", "fire": "999"},
    "United States": {"general": "911", "police": "911", "ambulance": "911", "fire": "911"},
    "Uruguay": {"general": "911", "police": "911", "ambulance": "911", "fire": "911"},
    "Vietnam": {"general": None, "police": "113", "ambulance": "115", "fire": "114"},
}


def _km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def country_near(lat: float, lng: float) -> str | None:
    """The country of the nearest catalog city, if one is within NEAR_KM."""
    best = min(catalog.DESTINATIONS, key=lambda d: _km(lat, lng, d["lat"], d["lng"]))
    return best["country"] if _km(lat, lng, best["lat"], best["lng"]) <= NEAR_KM else None


def country_named(value: str | None) -> str | None:
    """A country from a country name, an alias (UK, USA) or a catalog city code or name."""
    if not value:
        return None
    v = value.strip()
    by_name = {c.lower(): c for c in NUMBERS}
    if v.lower() in by_name:
        return by_name[v.lower()]
    if v.lower() in catalog.COUNTRY_ALIASES:
        return catalog.COUNTRY_ALIASES[v.lower()]
    dest = catalog.resolve(v)
    return dest["country"] if dest else None


def lookup(country: str | None = None, lat: float | None = None, lng: float | None = None) -> dict:
    """Emergency numbers for a named country or a position; `found` is False when neither gives a known country."""
    name = country_named(country) if country else None
    if not name and lat is not None and lng is not None:
        name = country_near(lat, lng)
    numbers = NUMBERS.get(name) if name else None
    return {
        "found": numbers is not None,
        "country": name if numbers else None,
        "numbers": numbers,
        "countries": sorted(NUMBERS),
        "verified": VERIFIED,
        "note": "Numbers can change. Confirm them locally, for example at your hotel. From a mobile, 112 also connects "
                "to emergency services in Europe and many other countries.",
    }
