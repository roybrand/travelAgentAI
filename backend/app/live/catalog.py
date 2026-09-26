"""The 109 selectable destinations plus a dynamic world-place fallback.

`code` is the IATA city/airport code (also what Amadeus expects). `cost` is a rough price level
1 (cheap) to 4 (expensive) used only by the price ESTIMATOR. `wiki` overrides the Wikipedia article
title when the plain city name is ambiguous. Coordinates are city centres.
"""
import re
import os
import time
import zlib

from app.live.http import DAY, cached, client

EUROPE, AMERICAS, ASIA, OCEANIA = "Europe", "Americas", "Asia", "Oceania"

# (code, city, country, lat, lng, cost, wiki title or None)
_EUROPE = [
    ("LON", "London", "United Kingdom", 51.5074, -0.1278, 4, None),
    ("PAR", "Paris", "France", 48.8566, 2.3522, 4, None),
    ("ROM", "Rome", "Italy", 41.9028, 12.4964, 3, None),
    ("MIL", "Milan", "Italy", 45.4642, 9.1900, 3, None),
    ("NAP", "Naples", "Italy", 40.8518, 14.2681, 2, None),
    ("VCE", "Venice", "Italy", 45.4408, 12.3155, 4, None),
    ("FLR", "Florence", "Italy", 43.7696, 11.2558, 3, None),
    ("BCN", "Barcelona", "Spain", 41.3874, 2.1686, 3, None),
    ("MAD", "Madrid", "Spain", 40.4168, -3.7038, 3, None),
    ("SVQ", "Seville", "Spain", 37.3891, -5.9845, 2, None),
    ("VLC", "Valencia", "Spain", 39.4699, -0.3763, 2, None),
    ("LIS", "Lisbon", "Portugal", 38.7223, -9.1393, 2, None),
    ("OPO", "Porto", "Portugal", 41.1579, -8.6291, 2, None),
    ("AMS", "Amsterdam", "Netherlands", 52.3676, 4.9041, 4, None),
    ("BRU", "Brussels", "Belgium", 50.8503, 4.3517, 3, None),
    ("BER", "Berlin", "Germany", 52.5200, 13.4050, 3, None),
    ("MUC", "Munich", "Germany", 48.1351, 11.5820, 3, None),
    ("VIE", "Vienna", "Austria", 48.2082, 16.3738, 3, None),
    ("PRG", "Prague", "Czechia", 50.0755, 14.4378, 2, None),
    ("BUD", "Budapest", "Hungary", 47.4979, 19.0402, 2, None),
    ("WAW", "Warsaw", "Poland", 52.2297, 21.0122, 2, None),
    ("KRK", "Krakow", "Poland", 50.0647, 19.9450, 1, "Kraków"),
    ("CPH", "Copenhagen", "Denmark", 55.6761, 12.5683, 4, None),
    ("STO", "Stockholm", "Sweden", 59.3293, 18.0686, 4, None),
    ("OSL", "Oslo", "Norway", 59.9139, 10.7522, 4, None),
    ("HEL", "Helsinki", "Finland", 60.1699, 24.9384, 3, None),
    ("DUB", "Dublin", "Ireland", 53.3498, -6.2603, 3, None),
    ("EDI", "Edinburgh", "United Kingdom", 55.9533, -3.1883, 3, None),
    ("ATH", "Athens", "Greece", 37.9838, 23.7275, 2, None),
    ("IBZ", "Ibiza", "Spain", 38.9067, 1.4206, 3, "Ibiza"),
    ("JTR", "Santorini", "Greece", 36.3932, 25.4615, 3, None),
    ("IST", "Istanbul", "Turkey", 41.0082, 28.9784, 2, None),
    ("DBV", "Dubrovnik", "Croatia", 42.6507, 18.0944, 3, None),
    ("SPU", "Split", "Croatia", 43.5081, 16.4402, 2, "Split, Croatia"),
    ("ZRH", "Zurich", "Switzerland", 47.3769, 8.5417, 4, None),
    ("GVA", "Geneva", "Switzerland", 46.2044, 6.1432, 4, None),
    ("NCE", "Nice", "France", 43.7102, 7.2620, 3, None),
    ("REK", "Reykjavik", "Iceland", 64.1466, -21.9426, 4, None),
    ("MLA", "Valletta", "Malta", 35.8989, 14.5146, 2, None),
    ("BEG", "Belgrade", "Serbia", 44.7866, 20.4489, 1, None),
    ("TLL", "Tallinn", "Estonia", 59.4370, 24.7536, 2, None),
]

_AMERICAS = [
    ("NYC", "New York", "United States", 40.7128, -74.0060, 4, "New York City"),
    ("LAX", "Los Angeles", "United States", 34.0522, -118.2437, 4, None),
    ("SFO", "San Francisco", "United States", 37.7749, -122.4194, 4, None),
    ("CHI", "Chicago", "United States", 41.8781, -87.6298, 3, None),
    ("MIA", "Miami", "United States", 25.7617, -80.1918, 3, None),
    ("LAS", "Las Vegas", "United States", 36.1699, -115.1398, 3, None),
    ("WAS", "Washington DC", "United States", 38.9072, -77.0369, 3, "Washington, D.C."),
    ("BOS", "Boston", "United States", 42.3601, -71.0589, 4, None),
    ("SEA", "Seattle", "United States", 47.6062, -122.3321, 3, None),
    ("MSY", "New Orleans", "United States", 29.9511, -90.0715, 2, None),
    ("YTO", "Toronto", "Canada", 43.6532, -79.3832, 3, None),
    ("YVR", "Vancouver", "Canada", 49.2827, -123.1207, 3, None),
    ("YMQ", "Montreal", "Canada", 45.5017, -73.5673, 3, None),
    ("MEX", "Mexico City", "Mexico", 19.4326, -99.1332, 2, None),
    ("CUN", "Cancun", "Mexico", 21.1619, -86.8515, 3, "Cancún"),
    ("HAV", "Havana", "Cuba", 23.1136, -82.3666, 2, None),
    ("SJU", "San Juan", "Puerto Rico", 18.4655, -66.1057, 3, "San Juan, Puerto Rico"),
    ("PTY", "Panama City", "Panama", 8.9824, -79.5199, 2, None),
    ("SJO", "San Jose", "Costa Rica", 9.9281, -84.0907, 2, "San José, Costa Rica"),
    ("BOG", "Bogota", "Colombia", 4.7110, -74.0721, 2, "Bogotá"),
    ("CTG", "Cartagena", "Colombia", 10.3910, -75.4794, 2, "Cartagena, Colombia"),
    ("MDE", "Medellin", "Colombia", 6.2442, -75.5812, 1, "Medellín"),
    ("LIM", "Lima", "Peru", -12.0464, -77.0428, 2, None),
    ("CUZ", "Cusco", "Peru", -13.5319, -71.9675, 2, None),
    ("SCL", "Santiago", "Chile", -33.4489, -70.6693, 2, None),
    ("BUE", "Buenos Aires", "Argentina", -34.6037, -58.3816, 2, None),
    ("RIO", "Rio de Janeiro", "Brazil", -22.9068, -43.1729, 2, None),
    ("SAO", "Sao Paulo", "Brazil", -23.5505, -46.6333, 2, "São Paulo"),
    ("MVD", "Montevideo", "Uruguay", -34.9011, -56.1645, 2, None),
    ("UIO", "Quito", "Ecuador", -0.1807, -78.4678, 1, None),
]

_ASIA = [
    ("TYO", "Tokyo", "Japan", 35.6762, 139.6503, 4, None),
    ("OSA", "Osaka", "Japan", 34.6937, 135.5023, 3, None),
    ("SEL", "Seoul", "South Korea", 37.5665, 126.9780, 3, None),
    ("PUS", "Busan", "South Korea", 35.1796, 129.0756, 2, None),
    ("BJS", "Beijing", "China", 39.9042, 116.4074, 2, None),
    ("SHA", "Shanghai", "China", 31.2304, 121.4737, 3, None),
    ("HKG", "Hong Kong", "China", 22.3193, 114.1694, 4, None),
    ("TPE", "Taipei", "Taiwan", 25.0330, 121.5654, 2, None),
    ("BKK", "Bangkok", "Thailand", 13.7563, 100.5018, 1, None),
    ("HKT", "Phuket", "Thailand", 7.8804, 98.3923, 2, "Phuket Province"),
    ("CNX", "Chiang Mai", "Thailand", 18.7883, 98.9853, 1, None),
    ("SIN", "Singapore", "Singapore", 1.3521, 103.8198, 4, None),
    ("KUL", "Kuala Lumpur", "Malaysia", 3.1390, 101.6869, 1, None),
    ("DPS", "Bali", "Indonesia", -8.6500, 115.2167, 2, "Bali"),
    ("JKT", "Jakarta", "Indonesia", -6.2088, 106.8456, 1, None),
    ("MNL", "Manila", "Philippines", 14.5995, 120.9842, 1, None),
    ("SGN", "Ho Chi Minh City", "Vietnam", 10.8231, 106.6297, 1, None),
    ("HAN", "Hanoi", "Vietnam", 21.0285, 105.8542, 1, None),
    ("DAD", "Da Nang", "Vietnam", 16.0544, 108.2022, 1, None),
    ("REP", "Siem Reap", "Cambodia", 13.3671, 103.8448, 1, None),
    ("DEL", "Delhi", "India", 28.6139, 77.2090, 1, None),
    ("BOM", "Mumbai", "India", 19.0760, 72.8777, 2, None),
    ("GOI", "Goa", "India", 15.2993, 74.1240, 1, "Goa"),
    ("CMB", "Colombo", "Sri Lanka", 6.9271, 79.8612, 1, None),
    ("MLE", "Male", "Maldives", 4.1755, 73.5093, 4, "Malé"),
    ("DXB", "Dubai", "United Arab Emirates", 25.2048, 55.2708, 4, None),
    ("AUH", "Abu Dhabi", "United Arab Emirates", 24.4539, 54.3773, 3, None),
    ("DOH", "Doha", "Qatar", 25.2854, 51.5310, 4, None),
    ("TLV", "Tel Aviv", "Israel", 32.0853, 34.7818, 4, None),
    ("AMM", "Amman", "Jordan", 31.9454, 35.9284, 2, None),
]

_OCEANIA = [
    ("SYD", "Sydney", "Australia", -33.8688, 151.2093, 4, None),
    ("MEL", "Melbourne", "Australia", -37.8136, 144.9631, 3, None),
    ("BNE", "Brisbane", "Australia", -27.4698, 153.0251, 3, None),
    ("PER", "Perth", "Australia", -31.9505, 115.8605, 3, "Perth, Western Australia"),
    ("ADL", "Adelaide", "Australia", -34.9285, 138.6007, 3, None),
    ("OOL", "Gold Coast", "Australia", -28.0167, 153.4000, 3, "Gold Coast, Queensland"),
    ("CNS", "Cairns", "Australia", -16.9186, 145.7781, 3, None),
    ("HBA", "Hobart", "Australia", -42.8821, 147.3272, 3, None),
]


def _build() -> list[dict]:
    out = []
    for region, rows in ((EUROPE, _EUROPE), (AMERICAS, _AMERICAS), (ASIA, _ASIA), (OCEANIA, _OCEANIA)):
        for code, city, country, lat, lng, cost, wiki in rows:
            out.append({
                "code": code, "city": city, "country": country, "region": region,
                "lat": lat, "lng": lng, "cost": cost, "wiki": wiki or city,
            })
    return out


DESTINATIONS: list[dict] = _build()
BY_CODE: dict[str, dict] = {d["code"]: d for d in DESTINATIONS}
WORLD = "World"


def _dyn_code(name: str, lat: float, lng: float) -> str:
    return f"GEO{zlib.crc32(f'{name}:{lat:.3f}:{lng:.3f}'.encode()) % 1000000:06d}"


def _dynamic_place(value: str) -> dict | None:
    if os.environ.get("WAYFINDER_OFFLINE") == "1":
        return None
    q = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(q) < 2:
        return None

    def fetch():
        with client(30) as c:
            r = c.get("https://nominatim.openstreetmap.org/search", params={
                "q": q, "format": "jsonv2", "limit": 1, "addressdetails": 1, "extratags": 1,
            })
            r.raise_for_status()
            time.sleep(1.1)
            return r.json()

    try:
        rows = cached(f"geocode_place_{q}", 30 * DAY, fetch)
    except Exception:
        return None
    if not rows:
        return None
    row = rows[0]
    try:
        lat, lng = float(row["lat"]), float(row["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    address = row.get("address") or {}
    city = row.get("name") or q
    country = address.get("country") or ""
    return {
        "code": _dyn_code(city, lat, lng),
        "city": city,
        "country": country,
        "region": WORLD,
        "lat": lat,
        "lng": lng,
        "cost": 3,
        "wiki": city,
        "dynamic": True,
        "query": q,
    }


def resolve(value: str | None) -> dict | None:
    """Find a destination by IATA code/city name, or geocode a world place dynamically."""
    if not value:
        return None
    v = value.strip()
    if v.upper() in BY_CODE:
        return BY_CODE[v.upper()]
    low = v.lower()
    fixed = next((d for d in DESTINATIONS if d["city"].lower() == low), None)
    return fixed or _dynamic_place(v)


COUNTRY_ALIASES = {
    "uk": "United Kingdom", "britain": "United Kingdom", "great britain": "United Kingdom", "england": "United Kingdom",
    "scotland": "United Kingdom", "usa": "United States", "us": "United States", "america": "United States",
    "united states of america": "United States", "uae": "United Arab Emirates", "emirates": "United Arab Emirates",
    "holland": "Netherlands", "the netherlands": "Netherlands", "czech republic": "Czechia", "korea": "South Korea",
}
_AMBIGUOUS_CITY_WORDS = {"male", "nice", "split", "lima", "reading"}  # ordinary words that are also city names


def _plain(text: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def find_in_text(text: str) -> dict:
    """Which catalog cities and countries a piece of free text names, matched on whole words and ignoring accents.
    Ordinary words that are also city names (nice, split, male, lima) are skipped: the language model handles those."""
    import re
    plain = _plain(text or "")

    def has(word: str) -> bool:
        return re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", plain) is not None

    cities = [d for d in DESTINATIONS
              if any(has(n) for n in {_plain(d["city"]), _plain(d["wiki"])} if n not in _AMBIGUOUS_CITY_WORDS)]
    countries = {d["country"] for d in DESTINATIONS if has(_plain(d["country"]))}
    countries |= {c for alias, c in COUNTRY_ALIASES.items() if has(alias)}
    return {"cities": cities, "countries": sorted(countries)}


def cities_in(country: str) -> list[dict]:
    return [d for d in DESTINATIONS if d["country"] == country]


def public_list() -> list[dict]:
    """What the API exposes to the UI (no internal fields)."""
    return [{k: d[k] for k in ("code", "city", "country", "region", "lat", "lng")} for d in DESTINATIONS]
