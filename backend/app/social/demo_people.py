"""DEMO people: a labelled pool of made-up travelers in Ibiza, Barcelona, Tel Aviv, Berlin and Paris, so Wayfinder People
can be shown before real people join.

Everything here is invented and marked as such:
- profiles carry a "demo" flag that is shown on every card, and use @wayfinder.invalid emails;
- pictures are AI-generated portraits of fictional people (scripts/generate_demo_photos.py) or, where none was made, drawings
  (see avatars.py). Never photographs of real people, and marked "AI" in the app;
- when someone says hi to a demo profile it accepts at once and replies with canned lines, and the chat says so.

The pool is STATIC (100 fixed profiles with fixed interests, ages and genders) and DYNAMIC: every day it posts fresh
night-life and sport requests, and when a real person posts a request nearby, a few demo people who fit it (and any gender
or age filter it uses) post a matching one, so the demo always has someone to meet. Nothing here runs unless demo
profiles exist, so a real launch simply never seeds them (or removes them with `scripts/seed_people.py --remove`).
"""
import json
import random
import time
from datetime import date, datetime, timedelta, timezone

from app.live import catalog
from app.live.geo import haversine_m
from app.partners import db, security
from app.social import intents, places, users, vocab

CITIES = ["IBZ", "BCN", "TLV", "BER", "PAR"]
EMAIL_DOMAIN = "wayfinder.invalid"
SEED = 2026

# (country, languages, women, men, non-binary)
ORIGINS = [
    ("Spain", ["Spanish", "English"], ["Lucia", "Carmen", "Paula", "Marta"], ["Javier", "Pablo", "Sergio", "Diego"], ["Alex"]),
    ("Italy", ["Italian", "English"], ["Giulia", "Chiara", "Elena", "Sofia"], ["Marco", "Luca", "Matteo", "Andrea"], ["Sasha"]),
    ("France", ["French", "English"], ["Camille", "Manon", "Chloe", "Ines"], ["Antoine", "Hugo", "Louis", "Theo"], ["Eden"]),
    ("Germany", ["German", "English"], ["Lena", "Hannah", "Mia", "Greta"], ["Jonas", "Felix", "Lukas", "Max"], ["Robin"]),
    ("United Kingdom", ["English"], ["Emily", "Charlotte", "Zoe", "Amelia"], ["Oliver", "Harry", "Jack", "Callum"], ["Charlie"]),
    ("Israel", ["Hebrew", "English"], ["Noa", "Maya", "Shira", "Tamar"], ["Itai", "Yonatan", "Omer", "Guy"], ["Noam"]),
    ("Brazil", ["Portuguese", "English"], ["Beatriz", "Larissa", "Juliana", "Camila"], ["Rafael", "Gabriel", "Thiago", "Bruno"], ["Dani"]),
    ("Argentina", ["Spanish", "English"], ["Valentina", "Agustina", "Micaela"], ["Facundo", "Tomas", "Nicolas"], ["Ari"]),
    ("Mexico", ["Spanish", "English"], ["Ximena", "Daniela", "Regina"], ["Emiliano", "Santiago", "Mateo"], ["Sol"]),
    ("United States", ["English"], ["Ashley", "Brianna", "Jasmine", "Taylor"], ["Tyler", "Jordan", "Marcus", "Ethan"], ["Riley"]),
    ("Canada", ["English", "French"], ["Chloe", "Sydney", "Brooke"], ["Liam", "Noah", "Connor"], ["Quinn"]),
    ("Australia", ["English"], ["Matilda", "Isla", "Tahlia"], ["Jack", "Lachlan", "Mitchell"], ["Kai"]),
    ("Sweden", ["Swedish", "English"], ["Astrid", "Freja", "Elsa"], ["Oskar", "Elias", "Axel"], ["Kim"]),
    ("Netherlands", ["Dutch", "English"], ["Sanne", "Fleur", "Lotte"], ["Daan", "Bram", "Sem"], ["Jules"]),
    ("Poland", ["Polish", "English"], ["Zofia", "Kasia", "Ola"], ["Kuba", "Marek", "Bartek"], ["Sam"]),
    ("Turkey", ["Turkish", "English"], ["Elif", "Zeynep", "Defne"], ["Emre", "Can", "Baris"], ["Deniz"]),
    ("Lebanon", ["Arabic", "French", "English"], ["Nour", "Layal", "Rima"], ["Karim", "Elie", "Rami"], ["Yara"]),
    ("Morocco", ["Arabic", "French"], ["Salma", "Imane", "Lina"], ["Youssef", "Amine", "Ilyas"], ["Sami"]),
    ("Nigeria", ["English"], ["Ada", "Ngozi", "Temi"], ["Chidi", "Tunde", "Emeka"], ["Ife"]),
    ("Ghana", ["English"], ["Ama", "Abena", "Efua"], ["Kwame", "Kofi", "Yaw"], ["Kojo"]),
    ("India", ["Hindi", "English"], ["Priya", "Ananya", "Meera"], ["Arjun", "Rohan", "Vikram"], ["Rishi"]),
    ("Japan", ["Japanese", "English"], ["Yuki", "Hana", "Aiko"], ["Kenji", "Ren", "Haruto"], ["Ryo"]),
    ("South Korea", ["Korean", "English"], ["Ji-woo", "Soo-min", "Hae-in"], ["Min-jun", "Joon", "Seo-jun"], ["Ha-neul"]),
    ("China", ["Chinese", "English"], ["Mei", "Lin", "Xiaoyu"], ["Wei", "Jian", "Hao"], ["Bao"]),
    ("Thailand", ["Thai", "English"], ["Ploy", "Nok", "Fah"], ["Somchai", "Arm", "Bank"], ["Ton"]),
    ("Greece", ["Greek", "English"], ["Eleni", "Katerina", "Maria"], ["Nikos", "Giorgos", "Dimitris"], ["Andy"]),
    ("Russia", ["Russian", "English"], ["Anya", "Katya", "Dasha"], ["Ivan", "Dima", "Misha"], ["Sasha"]),
]

# archetype -> (interests to draw from, hobbies for the bio, request templates)
# a template is (text, tags, day offset, part)
ARCHETYPES = {
    "clubber": (
        ["nightlife", "live-music", "photography"],
        ["dancing until sunrise", "techno since 2009", "DJing on weekends", "vinyl digging", "festival hopping", "making playlists", "house music"],
        [("Techno night tonight, looking for people to go dancing with", ["nightlife"], 0, "night"),
         ("Bar hopping and drinks tonight, relaxed and social", ["nightlife"], 0, "night"),
         ("Live music and drinks tonight", ["live-music", "nightlife"], 0, "evening"),
         ("Sunset drinks then clubbing tomorrow night", ["nightlife"], 1, "night"),
         ("Club night tonight, energetic crowd please", ["nightlife"], 0, "night")]),
    "sporty": (
        ["sports", "running", "cycling", "yoga", "beach"],
        ["running along the sea", "padel", "beach volleyball", "boxing", "climbing", "cycling", "morning yoga", "pickup football"],
        [("Morning run tomorrow, easy pace, happy to chat", ["running"], 1, "morning"),
         ("Padel doubles this evening, need one more", ["sports"], 0, "evening"),
         ("Beach volleyball this afternoon", ["sports", "beach"], 0, "afternoon"),
         ("Yoga session tomorrow morning", ["yoga"], 1, "morning"),
         ("Pickup football tonight", ["sports"], 0, "evening"),
         ("Cycling route tomorrow morning", ["cycling"], 1, "morning")]),
    "foodie": (
        ["food", "wine", "coffee", "shopping"],
        ["street food", "natural wine", "cooking", "coffee geek", "tasting menus", "food markets"],
        [("Dinner and wine tonight, somewhere local", ["food", "wine"], 0, "evening"),
         ("Street food tour tomorrow afternoon", ["food"], 1, "afternoon"),
         ("Coffee and a chat tomorrow morning", ["coffee"], 1, "morning"),
         ("Tapas and drinks tonight, relaxed", ["food", "nightlife"], 0, "evening"),
         ("Market and brunch this morning", ["food", "shopping"], 0, "morning")]),
    "culture": (
        ["museums", "art", "sightseeing", "photography"],
        ["street photography", "old bookshops", "architecture", "museums", "film photography", "sketching"],
        [("Museum this afternoon and then coffee", ["museums", "coffee"], 0, "afternoon"),
         ("Photo walk tomorrow morning", ["photography", "sightseeing"], 1, "morning"),
         ("Gallery hopping tomorrow, curious and cultural", ["art", "museums"], 1, "afternoon"),
         ("Old town walk this evening", ["sightseeing"], 0, "evening")]),
    "nature": (
        ["hiking", "beach", "diving", "cycling"],
        ["hiking", "snorkelling", "kayaking", "sunrise swims", "camping", "surfing"],
        [("Hike tomorrow morning, need company", ["hiking"], 1, "morning"),
         ("Beach and swimming this afternoon", ["beach"], 0, "afternoon"),
         ("Snorkelling tomorrow morning", ["diving", "beach"], 1, "morning"),
         ("Kayak trip tomorrow, adventurous", ["diving"], 1, "morning")]),
    "social": (
        ["language-exchange", "board-games", "coffee", "volunteering"],
        ["language exchange", "board games", "quiz nights", "volunteering", "meeting new people", "learning languages"],
        [("Language exchange over coffee this evening", ["language-exchange", "coffee"], 0, "evening"),
         ("Board games night tonight", ["board-games"], 0, "night"),
         ("Coffee tonight, just chatting", ["coffee"], 0, "evening"),
         ("Quiz night tonight, need a team", ["board-games", "nightlife"], 0, "night")]),
}
ARCH_WEIGHTS = {  # by age band: clubbers are younger, culture and food older
    "18-24": {"clubber": 5, "sporty": 3, "foodie": 1, "culture": 1, "nature": 2, "social": 2},
    "25-34": {"clubber": 4, "sporty": 3, "foodie": 3, "culture": 2, "nature": 2, "social": 2},
    "35-44": {"clubber": 2, "sporty": 3, "foodie": 3, "culture": 3, "nature": 3, "social": 2},
    "45-54": {"clubber": 1, "sporty": 2, "foodie": 4, "culture": 4, "nature": 3, "social": 2},
    "55+": {"clubber": 1, "sporty": 2, "foodie": 3, "culture": 5, "nature": 4, "social": 3},
}
BAND_AGES = {"18-24": (18, 24), "25-34": (25, 34), "35-44": (35, 44), "45-54": (45, 54), "55+": (55, 68)}
BAND_MIX = ["18-24"] * 24 + ["25-34"] * 34 + ["35-44"] * 20 + ["45-54"] * 14 + ["55+"] * 8
GENDER_MIX = ["woman"] * 46 + ["man"] * 46 + ["non-binary"] * 8
ROLES = ["Here for {n} days.", "Living here for a few years.", "Digital nomad, here for the month.", "Living here, happy to show people around.",
         "Visiting friends this week.", "Working remotely from here.", "Long weekend away."]
REPLIES = [
    "Hi! Thanks for reaching out. That sounds fun. What time were you thinking?",
    "Yes, I'd like that. Shall we meet somewhere busy and public, and I'll bring a friend?",
    "Great idea. I'm around the centre most of the day. Where are you staying?",
    "Sounds good to me. Send me the place and the time and I'll be there.",
    "Love it. I'll check my plans and confirm in a bit.",
    "Perfect. See you there, and let's keep it relaxed.",
]
_last_refresh = 0.0


def portrait_dir():
    """Where scripts/generate_demo_photos.py puts the AI-generated portraits (next to the database, git-ignored)."""
    from app import config
    return config.db_path().parent / "demo_photos"


# ---------------------------------------------------------------- who is a demo person

def city_of(row) -> str | None:
    """The demo person's city, kept in the email as demo-<city>-<n>@..., so no extra column is needed."""
    parts = (row["email"] or "").split("@")[0].split("-")
    return parts[1].upper() if row["demo"] and len(parts) >= 3 else None


def exists() -> bool:
    with db.tx() as c:
        return c.execute("SELECT 1 FROM users WHERE demo = 1 LIMIT 1").fetchone() is not None


def _demo_rows(c, city: str | None = None):
    rows = c.execute("SELECT * FROM users WHERE demo = 1 AND status = 'active' AND visible = 1 AND under_review = 0").fetchall()
    return [r for r in rows if city is None or city_of(r) == city]


# ---------------------------------------------------------------- making the 100

def _persona(rng: random.Random, band: str, gender: str, city: str, year: int) -> dict:
    lo, hi = BAND_AGES[band]
    age = rng.randint(lo, hi)
    country, langs, women, men, nb = rng.choice(ORIGINS)
    name = rng.choice({"woman": women, "man": men, "non-binary": nb}[gender])
    weights = ARCH_WEIGHTS[band]
    arch = rng.choices(list(weights), weights=list(weights.values()))[0]
    pool, hobbies, _templates = ARCHETYPES[arch]
    interests = rng.sample(pool, k=min(len(pool), rng.randint(2, 3)))
    extra = rng.choice([a for a in vocab.ACTIVITIES if a not in interests])
    interests.append(extra)
    h1, h2 = rng.sample(hobbies, 2)
    role = rng.choice(ROLES).format(n=rng.choice([3, 5, 7, 10]))
    city_name = catalog.BY_CODE[city]["city"]
    bio = f"From {country}, in {city_name}. {role} Into {h1} and {h2}."[:280]
    return {
        "name": f"{name} {chr(rng.randrange(65, 91))}.", "gender": gender if rng.random() < 0.92 else None, "age": age, "birth_year": year - age,
        "show_age": rng.random() < 0.6, "country": country, "languages": list(dict.fromkeys(langs + ([rng.choice(vocab.LANGUAGES)] if rng.random() < 0.3 else [])))[:4],
        "arch": arch, "interests": interests[:5], "bio": bio, "city": city,
    }


def seed(count: int = 100) -> dict:
    """Create `count` demo profiles, an equal share in each of the five cities, then give them today's requests and plans."""
    rng = random.Random(SEED)
    bands, genders = BAND_MIX[:], GENDER_MIX[:]   # shuffled once, so each city gets a spread of ages and genders
    rng.shuffle(bands)
    rng.shuffle(genders)
    year = date.today().year
    shared_hash = security.hash_password("demo-profile-not-a-real-login")
    made = {c: 0 for c in CITIES}
    now = datetime.now(timezone.utc).isoformat()
    with db.tx() as c:
        have = c.execute("SELECT COUNT(*) FROM users WHERE demo = 1").fetchone()[0]
        for i in range(have, count):
            city = CITIES[i % len(CITIES)]
            p = _persona(rng, bands[i % len(bands)], genders[i % len(genders)], city, year)
            c.execute(
                "INSERT INTO users (email, display_name, password_hash, birth_year, bio, interests, languages, home_city, photo_status, visible, "
                "gender, show_age, demo, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'approved', 1, ?, ?, 1, ?)",
                (f"demo-{city.lower()}-{i + 1:03d}@{EMAIL_DOMAIN}", p["name"], shared_hash, p["birth_year"], p["bio"], json.dumps(p["interests"]),
                 json.dumps(p["languages"]), p["country"], p["gender"], int(p["show_age"]), now))
            made[city] += 1
    refresh_pool(force=True)
    return made


def remove() -> int:
    with db.tx() as c:
        return c.execute("DELETE FROM users WHERE demo = 1").rowcount


# ---------------------------------------------------------------- posting requests (static seed and daily refresh)

def _archetype_of(row) -> str:
    """Pick the archetype whose interests overlap most with the person's."""
    mine = set(json.loads(row["interests"]))
    return max(ARCHETYPES, key=lambda a: (len(mine & set(ARCHETYPES[a][0])), a == "clubber"))


def _center(city: str) -> tuple[float, float]:
    d = catalog.BY_CODE[city]
    return d["lat"], d["lng"]


def _post(row, text: str, tags: list[str], day: date, part: str, lat: float, lng: float, radius_m: int) -> int:
    parsed = {"tags": tags, "languages": [], "vibes": [], "day": day, "part": part, "summary": text[:140], "want_genders": [], "want_ages": []}
    return _create_intent(row["id"], text, lat, lng, radius_m, parsed)


def _create_intent(user_id: int, text: str, lat: float, lng: float, radius_m: int, parsed: dict) -> int:
    """Like intents.create but without the per-day cap that protects real people from spamming."""
    now = datetime.now(timezone.utc).isoformat()
    with db.tx() as c:
        cur = c.execute(
            "INSERT INTO intents (user_id, text, tags, languages, vibes, want_genders, want_ages, summary, day, part, lat, lng, radius_m, created_at) "
            "VALUES (?, ?, ?, '[]', '[]', '[]', '[]', ?, ?, ?, ?, ?, ?, ?)",
            (user_id, text, json.dumps(parsed["tags"]), parsed["summary"], parsed["day"].isoformat(), parsed["part"],
             intents.coarse(lat), intents.coarse(lng), radius_m, now))
        return cur.lastrowid


def _open_days(c, user_id: int) -> set[str]:
    return {r["day"] for r in c.execute("SELECT day FROM intents WHERE user_id = ? AND status = 'open' AND day >= ?",
                                        (user_id, date.today().isoformat())).fetchall()}


def _venues(city: str, arch: str) -> list[dict]:
    """Real venues from OpenStreetMap (cached), so demo people appear in the same 'who is going' lists as real ones."""
    try:
        from app.live import osm
        kind = "nightclub" if arch == "clubber" else "pub"
        grouped = osm.places_of_type(catalog.BY_CODE[city], [kind], per_type=12)
        return grouped.get(kind, [])
    except Exception:
        return []


def refresh_pool(force: bool = False) -> int:
    """Give every demo person a request for today or tomorrow if they have none, and put the night-life crowd on real venues.
    Cheap and safe to call often: it does nothing more than once an hour unless forced."""
    global _last_refresh
    if not force and time.time() - _last_refresh < 3600:
        return 0
    _last_refresh = time.time()
    made = 0
    today = date.today()
    with db.tx() as c:
        rows = _demo_rows(c)
        busy = {r["id"]: _open_days(c, r["id"]) for r in rows}
    venue_cache: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        city = city_of(row)
        if not city:
            continue
        rng = random.Random(f"{SEED}-{row['id']}-{today.isoformat()}")
        arch = _archetype_of(row)
        if not busy[row["id"]]:
            text, tags, offset, part = rng.choice(ARCHETYPES[arch][2])
            lat, lng = _center(city)
            _post(row, text, tags, today + timedelta(days=offset), part, lat + rng.uniform(-0.012, 0.012), lng + rng.uniform(-0.012, 0.012), rng.choice([3000, 5000, 8000]))
            made += 1
        if arch in ("clubber", "foodie") and rng.random() < 0.7:
            key = (city, arch)
            venue_cache.setdefault(key, _venues(city, arch))
            venues = venue_cache[key]
            if venues:
                v = rng.choice(venues[:8])
                try:
                    places.attend(row["id"], v["id"], v["name"], v["type"], city, v["lat"], v["lng"], today)
                except places.PlaceError:
                    pass
    return made


# ---------------------------------------------------------------- dynamic matching for a real person

def attune(viewer_id: int, intent) -> int:
    """A real person posted a request: a few demo people nearby who fit it (and any gender or age filter) post a matching
    one for the same day, so the demo always has someone to meet. Returns how many were created."""
    viewer = users.get_row(viewer_id)
    if not viewer or viewer["demo"] or not exists():
        return 0
    city = min(CITIES, key=lambda c: haversine_m(intent["lat"], intent["lng"], *_center(c)))
    if haversine_m(intent["lat"], intent["lng"], *_center(city)) > 35_000:
        return 0
    tags = json.loads(intent["tags"])
    want_genders, want_ages = json.loads(intent["want_genders"]), json.loads(intent["want_ages"])
    day = date.fromisoformat(intent["day"])
    rng = random.Random(f"{viewer_id}-{intent['id']}")
    with db.tx() as c:
        pool = _demo_rows(c, city)
        have = {r["user_id"] for r in c.execute("SELECT user_id FROM intents WHERE status = 'open' AND day = ?", (day.isoformat(),)).fetchall()}
    hidden = users.hidden_ids(viewer_id)
    fits = [r for r in pool if r["id"] not in hidden and users.allowed(viewer, r) and users.passes(r, want_genders, want_ages)]
    # people whose interests overlap come first; a few are picked at random within that so it varies per request
    fits.sort(key=lambda r: (-len(set(json.loads(r["interests"])) & set(tags)), rng.random()))
    created = 0
    for row in fits:
        if created >= 4:
            break
        if row["id"] in have:
            continue
        shared = [t for t in tags if t in json.loads(row["interests"])] or tags[:1]
        options = [t for a in ARCHETYPES.values() for t in a[2] if set(t[1]) & set(shared)]
        if not options:
            continue
        text, ttags, _offset, part = rng.choice(options)
        part = intent["part"] if intent["part"] != "any" else part
        radius = max(intent["radius_m"], 3000)
        jitter = min(intent["radius_m"], 2000) / 111_000 / 2
        _post(row, text, ttags, day, part, intent["lat"] + rng.uniform(-jitter, jitter), intent["lng"] + rng.uniform(-jitter, jitter), radius)
        created += 1
    return created


# ---------------------------------------------------------------- talking to a demo person

def welcome(row) -> str:
    return f"Hi! I'm {row['display_name'].split()[0]}. Thanks for the request. Happy to plan something. What time suits you?"


def reply(row, n_messages: int) -> str:
    return REPLIES[n_messages % len(REPLIES)]
