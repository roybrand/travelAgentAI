"""Seeded showcase routes for demos and QA.

The normal planner is dynamic. This module adds one intentionally rich test route:
10 days from Paris to Rome to Athens, split into broad equal-distance route days, with
four suggested stops per day and demo community content.
"""
import math
from datetime import date
from urllib.parse import quote

from app.live import catalog
from app.partners import db
from app.place_reviews import upsert_place

SHOWCASE_CODES = ["PAR", "ROM", "ATH"]
PARTS = ["morning", "afternoon", "evening", "night"]
PART_LABEL = {"morning": "Morning", "afternoon": "Noon", "evening": "Evening", "night": "Night"}
PLACE_TYPES = ["historic", "museum", "park", "viewpoint", "restaurant", "cafe", "pub", "nightclub", "theatre", "market"]
REVIEW_TEMPLATES = [
    (5, "Worth building the day around. Easy to understand why locals recommend it, and the stop felt memorable rather than filler."),
    (4, "Good stop with enough nearby streets and cafes to make it feel like part of the route, not just a pin on the map."),
    (5, "Beautiful setting and a useful break in the travel day. I would leave a little extra time here."),
]
VERIFIED_COMMONS_FILES = {
    "Louvre_Museum_Wikimedia_Commons.jpg",
    "Notre-Dame_de_Paris,_4_October_2017.jpg",
    "Le_Caveau_de_la_Huchette.jpg",
    "Halles_de_Dijon.JPG",
    "Colosseum_in_Rome,_Italy_-_April_2007.jpg",
    "St_Peter's_Square,_Vatican_City_-_April_2007.jpg",
    "Pompeii_Street.jpg",
    "Castel_dell'Ovo_Naples.jpg",
    "The_Parthenon_in_Athens.jpg",
}


def is_paris_rome_athens(req: dict, nights: int) -> bool:
    route = [str(x).upper() for x in (req.get("destinations") or [req.get("destination")])]
    return nights == 10 and route[:3] == SHOWCASE_CODES


def _route_points() -> list[dict]:
    out = []
    for code in SHOWCASE_CODES:
        d = catalog.resolve(code)
        out.append({"code": code, "name": d["city"], "lat": d["lat"], "lng": d["lng"], "country": d["country"]})
    return out


def _distance(a: dict, b: dict) -> float:
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlat = lat2 - lat1
    dlng = math.radians(b["lng"] - a["lng"])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(h))


def _point_at(points: list[dict], progress: float) -> dict:
    lengths = [_distance(a, b) for a, b in zip(points, points[1:])]
    total = sum(lengths) or 1
    left = max(0, min(1, progress)) * total
    for idx, length in enumerate(lengths):
        if left <= length or idx == len(lengths) - 1:
            a, b = points[idx], points[idx + 1]
            t = left / length if length else 0
            return {
                "name": a["name"] if t < 0.08 else b["name"] if t > 0.92 else f"{a['name']} to {b['name']}",
                "lat": a["lat"] + (b["lat"] - a["lat"]) * t,
                "lng": a["lng"] + (b["lng"] - a["lng"]) * t,
                "country": a["country"] if t < 0.5 else b["country"],
                "progress": progress,
            }
        left -= length
    return {**points[-1], "progress": 1}


def _section_label(day: int, nights: int) -> str:
    points = _route_points()
    lengths = [_distance(a, b) for a, b in zip(points, points[1:])]
    total = sum(lengths) or 1
    mid = ((day - 0.5) / nights) * total
    done = 0
    for idx, length in enumerate(lengths):
        if mid <= done + length or idx == len(lengths) - 1:
            return f"{points[idx]['name']}-{points[idx + 1]['name']} section {day}"
        done += length
    return f"Paris-Rome-Athens section {day}"


def _commons(file_name: str) -> str:
    if file_name.startswith("http://") or file_name.startswith("https://"):
        return file_name
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(file_name)}?width=900"


def _photo(file_name: str, author: str = "Wikimedia Commons contributors", license_name: str = "Creative Commons or public domain") -> dict:
    if not file_name.startswith(("http://", "https://")) and file_name not in VERIFIED_COMMONS_FILES:
        return {}
    return {
        "photo_url": _commons(file_name),
        "photo_credit": {"source": "Wikimedia Commons", "author": author, "license": license_name},
    }


def _activity(day: int, part: str, name: str, typ: str, type_label: str, city: str, country: str, lat: float, lng: float,
              why: str, tags: list[str], *, duration: str = "1-2 hours", cost: str | None = None,
              website: str | None = None, url: str | None = None, photo: tuple[str, str, str] | None = None,
              notes: dict | None = None) -> dict:
    day_start = (day - 1) / 10
    local = (PARTS.index(part) + 0.5) / len(PARTS)
    progress = day_start + local / 10
    payload = {
        "key": f"showcase-route:{day}:{part}:{name}",
        "source": "showcase-route",
        "fixed_day": day,
        "day": day,
        "default_part": part,
        "name": name,
        "type": typ,
        "typeLabel": type_label,
        "city": city,
        "country": country,
        "area": _section_label(day, 10),
        "destination": None,
        "lat": lat,
        "lng": lng,
        "route_progress": round(local, 3),
        "global_route_progress": round(progress, 3),
        "distance_to_route_m": 0,
        "why": why,
        "duration": duration,
        "cost": cost,
        "website": website,
        "url": url,
        "tags": list(dict.fromkeys([*tags, part, "route"])),
        "matches": list(dict.fromkeys(tags[:5] + ["route"])),
        "showcase_notes": notes or {},
    }
    if photo:
        payload.update(_photo(*photo))
    return payload


CURATED_ACTIVITIES = [
    _activity(1, "morning", "Louvre Museum and Cour Carree", "museum", "Museum", "Paris", "France", 48.8606, 2.3376,
              "Start with a world-class museum and the palace courtyards before the route leaves Paris.", ["art", "history", "museum"],
              cost="Timed tickets often from EUR 22", website="https://www.louvre.fr/en",
              photo=("Louvre_Museum_Wikimedia_Commons.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media"),
              notes={"history": "Former royal palace and one of the world's largest museums.", "discounts": "Under-18s and many EU residents under 26 are commonly eligible for free admission; check current rules."}),
    _activity(1, "afternoon", "Marche Bastille", "market", "Market", "Paris", "France", 48.8532, 2.3691,
              "A food-market lunch that keeps the first day local and flexible.", ["food-scene", "market", "local"],
              cost="Pay per stall", url="https://en.parisinfo.com/shopping-paris/73811/Marche-Bastille",
              photo=("Marche_Bastille,_Paris_2010.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(1, "evening", "Ile de la Cite and Notre-Dame exterior", "historic", "Historic site", "Paris", "France", 48.8530, 2.3499,
              "Golden-hour streets, river views and a compact history walk before dinner.", ["history", "architecture", "viewpoint"],
              cost="Free exterior walk", website="https://www.notredamedeparis.fr/en/",
              photo=("Notre-Dame_de_Paris,_4_October_2017.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(1, "night", "Le Caveau de la Huchette", "pub", "Jazz club", "Paris", "France", 48.8521, 2.3450,
              "A classic Paris night stop for jazz and dancing close to the Latin Quarter.", ["nightlife", "music", "jazz"],
              cost="Cover varies by night", website="https://www.caveaudelahuchette.fr/",
              photo=("Le_Caveau_de_la_Huchette.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media"),
              notes={"concerts": "Check the venue calendar for nightly jazz lineups."}),

    _activity(2, "morning", "Palace of the Dukes of Burgundy", "historic", "Historic palace", "Dijon", "France", 47.3212, 5.0415,
              "A strong Burgundy history anchor roughly one route-day from Paris.", ["history", "architecture", "museum"],
              website="https://musees.dijon.fr/musee-des-beaux-arts",
              photo=("https://thumb.wikimedia.org/wikipedia/commons/thumb/d/d7/Dijon_-_Palais_des_Ducs_et_des_%C3%89tats_de_Bourgogne_-_01.jpg/330px-Dijon_-_Palais_des_Ducs_et_des_%C3%89tats_de_Bourgogne_-_01.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(2, "afternoon", "Les Halles de Dijon", "market", "Covered market", "Dijon", "France", 47.3228, 5.0386,
              "A practical lunch stop for Burgundy produce, cheese, charcuterie and quick tastings.", ["food-scene", "market", "local"],
              cost="Pay per stall", photo=("Halles_de_Dijon.JPG", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(2, "evening", "Hospices de Beaune", "museum", "Historic museum", "Beaune", "France", 47.0221, 4.8367,
              "A vivid medieval hospital and wine-region landmark, useful before staying in Burgundy.", ["history", "wine", "museum"],
              cost="Ticketed", website="https://hospices-de-beaune.com/en/",
              photo=("https://thumb.wikimedia.org/wikipedia/commons/thumb/c/c2/Beaune_-_H%C3%B4tel-Dieu_-_Cour_-_05.jpg/330px-Beaune_-_H%C3%B4tel-Dieu_-_Cour_-_05.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(2, "night", "La Dilettante wine bar", "pub", "Wine bar", "Beaune", "France", 47.0232, 4.8381,
              "A low-key Burgundy night with local bottles and small plates.", ["wine", "nightlife", "food-scene"],
              cost="By glass/bottle", website="https://www.ladilettante-beaune.fr/"),

    _activity(3, "morning", "Vieux Lyon traboules", "historic", "Old town walk", "Lyon", "France", 45.7621, 4.8279,
              "A route-friendly morning through Renaissance lanes and covered passageways.", ["history", "architecture", "walking"],
              cost="Free self-guided walk", photo=("https://thumb.wikimedia.org/wikipedia/commons/thumb/4/4b/Vieuxlyon_saintjean_toits.jpg/330px-Vieuxlyon_saintjean_toits.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(3, "afternoon", "Les Halles de Lyon Paul Bocuse", "restaurant", "Food hall", "Lyon", "France", 45.7606, 4.8503,
              "The obvious Lyon lunch stop: charcuterie, oysters, cheese, pastries and counters.", ["food-scene", "market", "restaurant"],
              cost="Counter meals and tastings vary", website="https://www.halles-de-lyon-paulbocuse.com/",
              photo=("Les_Halles_de_Lyon-Paul_Bocuse.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(3, "evening", "Fourviere Basilica and Roman Theatres", "viewpoint", "Viewpoint and ruins", "Lyon", "France", 45.7623, 4.8227,
              "Sunset views over Lyon plus ancient theatre ruins in the same hilltop area.", ["viewpoint", "history", "architecture"],
              cost="Free exterior and ruins area", photo=("https://thumb.wikimedia.org/wikipedia/commons/thumb/7/70/Fourviere_Lyon.jpg/330px-Fourviere_Lyon.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(3, "night", "Croix-Rousse bars", "pub", "Bar district", "Lyon", "France", 45.7744, 4.8320,
              "A neighbourhood night with relaxed bars after the food-heavy afternoon.", ["nightlife", "pub", "local"],
              cost="Drinks by venue"),

    _activity(4, "morning", "Chambery old town and Elephants Fountain", "historic", "Historic centre", "Chambery", "France", 45.5663, 5.9204,
              "A compact Alpine foothills stop that breaks the Lyon-Turin crossing neatly.", ["history", "architecture", "walking"],
              cost="Free walk", photo=("https://thumb.wikimedia.org/wikipedia/commons/thumb/a/a2/Chamb%C3%A9ry_-_Place_St-L%C3%A9ger.JPG/330px-Chamb%C3%A9ry_-_Place_St-L%C3%A9ger.JPG", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(4, "afternoon", "Porta Palazzo Market", "market", "Market", "Turin", "Italy", 45.0794, 7.6827,
              "One of Europe's great food markets, ideal for a grazing lunch after crossing into Italy.", ["food-scene", "market", "local"],
              cost="Pay per stall", photo=("Porta_Palazzo_Torino.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(4, "evening", "Egyptian Museum of Turin", "museum", "Museum", "Turin", "Italy", 45.0689, 7.6842,
              "A major museum that gives the day cultural depth beyond the road transfer.", ["museum", "history", "art"],
              cost="Ticketed", website="https://museoegizio.it/en/",
              photo=("Museo_Egizio_Torino_01.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(4, "night", "San Salvario aperitivo", "pub", "Aperitivo district", "Turin", "Italy", 45.0586, 7.6812,
              "Turin's easygoing aperitivo zone, useful for bars, late bites and music listings.", ["nightlife", "food-scene", "pub"],
              cost="Aperitivo/drinks by venue"),

    _activity(5, "morning", "Genoa Old Port", "viewpoint", "Waterfront", "Genoa", "Italy", 44.4095, 8.9274,
              "A lively harbour stop with sea air, museums nearby and enough space for a route break.", ["viewpoint", "waterfront", "family"],
              cost="Free waterfront walk", photo=("Porto_Antico_Genova.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(5, "afternoon", "Mercato Orientale Genoa", "market", "Market", "Genoa", "Italy", 44.4074, 8.9407,
              "Lunch around focaccia, pesto, fish counters and quick Ligurian plates.", ["food-scene", "market", "local"],
              cost="Pay per stall", website="https://www.mercatoorientalegenova.it/",
              photo=("https://thumb.wikimedia.org/wikipedia/commons/thumb/0/0d/Piazza_de_Ferrari%2C_Genoa.jpg/330px-Piazza_de_Ferrari%2C_Genoa.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(5, "evening", "Piazza dei Miracoli", "historic", "Historic square", "Pisa", "Italy", 43.7230, 10.3966,
              "A clean evening route marker between Liguria and Tuscany, with the tower and cathedral complex.", ["history", "architecture", "viewpoint"],
              cost="Square is free; monuments ticketed", website="https://www.opapisa.it/en/",
              photo=("https://thumb.wikimedia.org/wikipedia/commons/thumb/0/03/Pisa-Piazza_dei_Miracoli-10-Totale_von_Baptisterium-1983-gje.jpg/330px-Pisa-Piazza_dei_Miracoli-10-Totale_von_Baptisterium-1983-gje.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(5, "night", "Santo Spirito nightlife", "pub", "Bar district", "Florence", "Italy", 43.7666, 11.2480,
              "Florence's Oltrarno side works well for a late arrival: bars, casual food and a local square.", ["nightlife", "pub", "local"],
              cost="Drinks by venue"),

    _activity(6, "morning", "Colosseum and Roman Forum", "historic", "Ancient site", "Rome", "Italy", 41.8902, 12.4922,
              "The clearest Rome history anchor and a strong start after reaching the city.", ["history", "architecture", "ancient"],
              cost="Ticketed; official timed entry recommended", website="https://colosseo.it/en/",
              photo=("Colosseum_in_Rome,_Italy_-_April_2007.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(6, "afternoon", "Campo de' Fiori and Jewish Ghetto food walk", "restaurant", "Food walk", "Rome", "Italy", 41.8956, 12.4722,
              "A lunch zone for markets, bakeries, fried artichokes, pasta and short history detours.", ["food-scene", "history", "walking"],
              cost="Self-guided, pay as you go", photo=("https://thumb.wikimedia.org/wikipedia/commons/thumb/3/37/Campo_dei_Fiori.jpg/330px-Campo_dei_Fiori.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(6, "evening", "St Peter's Square and Vatican exterior", "historic", "Landmark", "Vatican City", "Vatican City", 41.9022, 12.4539,
              "A grand dusk stop without needing to solve the museum queue on the same day.", ["history", "architecture", "viewpoint"],
              cost="Square is free", website="https://www.basilicasanpietro.va/en.html",
              photo=("St_Peter's_Square,_Vatican_City_-_April_2007.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(6, "night", "Trastevere pubs and live bars", "pub", "Nightlife district", "Rome", "Italy", 41.8896, 12.4700,
              "A dependable Rome night: pubs, wine bars, late food and occasional live sets.", ["nightlife", "pub", "music"],
              cost="By venue", notes={"parties": "Use this as the nightlife search area for pub crawls and live music."}),

    _activity(7, "morning", "Pompeii Archaeological Park", "historic", "Archaeological site", "Pompeii", "Italy", 40.7484, 14.4847,
              "A major ancient-history day stop on the Rome-to-southern-Italy leg.", ["history", "archaeology", "museum"],
              cost="Ticketed", website="https://pompeiisites.org/en/",
              photo=("Pompeii_Street.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(7, "afternoon", "Spaccanapoli and Naples pizza stop", "restaurant", "Food district", "Naples", "Italy", 40.8492, 14.2575,
              "A high-reward lunch route: old Naples streets, churches, espresso and pizza.", ["food-scene", "history", "walking"],
              cost="Pizza and cafe prices vary", photo=("Spaccanapoli_Napoli.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(7, "evening", "Castel dell'Ovo waterfront", "viewpoint", "Waterfront castle", "Naples", "Italy", 40.8283, 14.2475,
              "Sea views, castle walls and an easy promenade before continuing south.", ["viewpoint", "history", "waterfront"],
              cost="Exterior/free promenade", photo=("Castel_dell'Ovo_Naples.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(7, "night", "Chiaia and Piazza Bellini bars", "pub", "Bar district", "Naples", "Italy", 40.8499, 14.2510,
              "Two reliable Naples nightlife pockets: cocktails in Chiaia or student bars near Bellini.", ["nightlife", "pub", "music"],
              cost="By venue"),

    _activity(8, "morning", "Sassi di Matera viewpoints", "viewpoint", "Historic viewpoint", "Matera", "Italy", 40.6664, 16.6043,
              "A memorable detour toward Puglia with cave districts, viewpoints and deep history.", ["history", "viewpoint", "walking"],
              cost="Viewpoints free; cave churches ticketed", photo=("Matera_Sassi_2019.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(8, "afternoon", "Bari Vecchia and orecchiette lane", "market", "Old town food stop", "Bari", "Italy", 41.1275, 16.8719,
              "Lunch in Bari's old town, with fresh pasta lanes and quick street-food options.", ["food-scene", "market", "history"],
              cost="Pay as you go", photo=("Bari_vecchia_orecchiette.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(8, "evening", "Brindisi waterfront and Roman columns", "historic", "Port landmark", "Brindisi", "Italy", 40.6380, 17.9456,
              "A clear pre-ferry evening marker with harbour views and Roman road history.", ["history", "waterfront", "viewpoint"],
              cost="Free", photo=("Brindisi_colonne_romane.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(8, "night", "Overnight ferry to Greece", "attraction", "Ferry crossing", "Brindisi", "Italy", 40.6430, 17.9580,
              "Treat the night as transport plus a simple onboard dinner, then wake up on the Greek side.", ["transport", "waterfront", "route"],
              cost="Ferry prices vary; book cabins early in summer", notes={"discounts": "Ferry operators sometimes price early booking, youth/student and cabin bundles separately."}),

    _activity(9, "morning", "Patras waterfront and Agios Andreas", "historic", "Port city stop", "Patras", "Greece", 38.2466, 21.7346,
              "A practical landing point after the ferry with a short waterfront and church stop.", ["history", "waterfront", "architecture"],
              cost="Mostly free", photo=("Patras_-_Agios_Andreas.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(9, "afternoon", "Archaeological Site of Delphi", "historic", "Ancient site", "Delphi", "Greece", 38.4824, 22.5010,
              "One of the strongest history stops between the Greek west coast and Athens.", ["history", "archaeology", "viewpoint"],
              cost="Ticketed; combined museum/site ticket often available", website="https://www.culture.gov.gr/en/service/SitePages/view.aspx?iID=2695",
              photo=("Tholos_at_Delphi_2010.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(9, "evening", "Arachova mountain village", "restaurant", "Village dinner stop", "Arachova", "Greece", 38.4795, 22.5836,
              "A good dinner break after Delphi, known for mountain tavernas and winter nightlife.", ["food-scene", "local", "viewpoint"],
              cost="Taverna prices vary", photo=("https://thumb.wikimedia.org/wikipedia/commons/thumb/5/5c/GR-arachova.jpg/330px-GR-arachova.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(9, "night", "Psiri late bars", "pub", "Nightlife district", "Athens", "Greece", 37.9787, 23.7240,
              "If you reach Athens late, Psiri keeps the night easy: bars, music and casual food.", ["nightlife", "pub", "music"],
              cost="By venue"),

    _activity(10, "morning", "Acropolis and Parthenon", "historic", "Ancient site", "Athens", "Greece", 37.9715, 23.7267,
              "The essential Athens history stop; go early for heat, light and crowd control.", ["history", "archaeology", "viewpoint"],
              cost="Ticketed; seasonal pricing and combined tickets may apply", website="https://hhticket.gr/",
              photo=("The_Parthenon_in_Athens.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(10, "afternoon", "Athens Central Market", "market", "Market", "Athens", "Greece", 37.9801, 23.7263,
              "A punchy lunch stop for market halls, grill houses and nearby coffee.", ["food-scene", "market", "local"],
              cost="Pay by stall/restaurant", photo=("Athens_Central_Market.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(10, "evening", "Lycabettus Hill", "viewpoint", "Viewpoint", "Athens", "Greece", 37.9818, 23.7437,
              "The route's final sunset viewpoint, with the Acropolis and sea on the skyline.", ["viewpoint", "park", "walking"],
              cost="Walk free; funicular ticket optional", photo=("View_from_Lycabettus_Hill_Athens.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media")),
    _activity(10, "night", "Gazi and Technopolis nightlife", "nightclub", "Nightlife district", "Athens", "Greece", 37.9784, 23.7137,
              "A strong final-night base for clubs, bars, concerts and late food.", ["nightlife", "club", "music", "concerts"],
              cost="By venue/event", website="https://www.technopolis-athens.com/",
              photo=("Technopolis_Gazi_Athens.jpg", "Wikimedia Commons contributors", "CC-compatible Commons media"),
              notes={"concerts": "Technopolis and nearby venues are good targets for live event lookups."}),
]


def day_areas(nights: int = 10) -> list[dict]:
    points = _route_points()
    areas = []
    for day in range(1, nights + 1):
        start = _point_at(points, (day - 1) / nights)
        areas.append({
            "day": day,
            "country": start.get("country") or "",
            "label": _section_label(day, nights),
            "radius_m": 25000,
            "types": PLACE_TYPES,
        })
    return areas


def day_locations(nights: int = 10) -> list[dict]:
    # Sleep roughly along the showcase route: France/Burgundy/Lyon, northern Italy, Rome/Naples/Puglia, then Athens.
    codes = ["PAR", "PAR", "PAR", "ROM", "ROM", "ROM", "ROM", "ATH", "ATH", "ATH"]
    return [{"day": i + 1, "destination": codes[i]} for i in range(min(nights, len(codes)))]


def apply_request_defaults(req: dict, nights: int) -> dict:
    if not is_paris_rome_athens(req, nights):
        return req
    out = {**req}
    out["day_areas"] = out.get("day_areas") or day_areas(nights)
    out["day_locations"] = out.get("day_locations") or day_locations(nights)
    out["place_types"] = list(dict.fromkeys([*(out.get("place_types") or []), *PLACE_TYPES]))
    return out


class _PlaceShim:
    def __init__(self, data: dict):
        self._data = data
        for key, value in data.items():
            setattr(self, key, value)

    def __getattr__(self, _key):
        return None

    def model_dump(self):
        return self._data


def _seed_reviews(place: dict) -> None:
    row = upsert_place(_PlaceShim(place))
    with db.tx() as c:
        existing = c.execute("SELECT COUNT(*) FROM place_reviews WHERE place_id = ?", (row["id"],)).fetchone()[0]
        if existing:
            return
        ts = date.today().isoformat()
        for rating, body in REVIEW_TEMPLATES:
            c.execute(
                "INSERT INTO place_reviews (place_id, user_id, rating, body, visit_date, status, created_at, updated_at) "
                "VALUES (?, NULL, ?, ?, ?, 'approved', ?, ?)",
                (row["id"], rating, body, ts, ts, ts),
            )


def route_ideas(req: dict, nights: int) -> list[dict]:
    if not is_paris_rome_athens(req, nights):
        return []
    ideas = [dict(item) for item in CURATED_ACTIVITIES[:nights * len(PARTS)]]
    for item in ideas:
        _seed_reviews(item)
    return ideas


def seed_all_demo_reviews() -> None:
    for item in CURATED_ACTIVITIES:
        _seed_reviews(dict(item))


def inject_guide(guide: dict, req: dict, nights: int) -> dict:
    ideas = route_ideas(req, nights)
    if not ideas:
        return guide
    by_type = dict(guide.get("by_type") or {})
    by_type["showcase-route"] = {"label": "Paris-Rome-Athens showcase", "places": ideas}
    sources = dict(guide.get("sources") or {})
    sources["showcase-route"] = "Curated QA route seed with Wikimedia Commons photo links and demo Wayfinder reviews"
    return {
        **guide,
        "route_ideas": [*(guide.get("route_ideas") or []), *ideas],
        "by_type": by_type,
        "sources": sources,
    }
