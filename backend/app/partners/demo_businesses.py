"""DEMO businesses: 124 made-up partners with live deals across the world, so deals, alerts and the RSS feed can be shown
before real businesses join.

Everything is labelled: partner names start with "Demo · ", emails end in @wayfinder.invalid, booking links point at
example.com, and the deal pictures are drawn illustrations (see /api/deals/art). Deals go through the same tables and
ranking as real ones, and are approved on creation so they show at once.

STATIC: 124 businesses (8 each in Tel Aviv, Berlin, Barcelona, Paris and Ibiza, 3 each in 20 more cities, and 3 each in
8 Australian cities), each with a standing deal that runs for weeks or months, so trips a few months away still find deals. DYNAMIC: each day expired deals are renewed and about 30 businesses post a "Tonight only" flash deal.
Nothing runs unless demo businesses exist. Remove them with `python scripts/seed_demo.py --remove`.
"""
import random
import time
from datetime import date, datetime, timedelta, timezone

from app.live import catalog
from app.partners import db, deals, security

SEED = 4242
EMAIL_PREFIX = "demo-biz-"
EMAIL_DOMAIN = "wayfinder.invalid"
MAIN = ["TLV", "BER", "BCN", "PAR", "IBZ"]
AUSTRALIA = ["SYD", "MEL", "BNE", "PER", "ADL", "OOL", "CNS", "HBA"]
OTHERS = ["LON", "LIS", "ROM", "AMS", "MAD", "ATH", "IST", "DXB", "NYC", "MIA", "MEX", "RIO", "BUE", "TYO", "BKK", "SIN", "SEL", "LAX", "CPH", "VIE"]
CURRENCY = {"LON": "GBP", "PAR": "EUR", "BER": "EUR", "BCN": "EUR", "IBZ": "EUR", "LIS": "EUR", "ROM": "EUR", "AMS": "EUR", "MAD": "EUR",
            "ATH": "EUR", "VIE": "EUR"}
TYPE_MIX = ["restaurant"] * 26 + ["bar"] * 16 + ["party"] * 12 + ["tour"] * 12 + ["activity"] * 10 + ["spa"] * 8 + ["hotel"] * 10 + ["car_rental"] * 6
ADJ = ["Blue", "Golden", "Little", "Hidden", "Sunset", "Old", "Wild", "Velvet", "Salt", "Olive", "Neon", "Moon", "Copper", "Lazy", "Bright", "Secret"]
NOUN = {
    "restaurant": ["Table", "Kitchen", "Bistro", "Cantina", "Garden", "Grill"],
    "bar": ["Bar", "Cocktail Room", "Taproom", "Speakeasy", "Rooftop"],
    "party": ["Club", "Warehouse", "Terrace", "Disco", "Beach Club"],
    "tour": ["Walks", "Tours", "Trails", "Bike Tours"],
    "activity": ["Surf School", "Climbing Gym", "Kayak Co", "Padel Club", "Dive Centre"],
    "spa": ["Spa", "Hammam", "Wellness House", "Thermal Baths"],
    "hotel": ["Hotel", "Boutique Hotel", "Hostel", "Lofts"],
    "car_rental": ["Car Hire", "Rentals", "Wheels"],
}
# category -> (title, description, price low-high, discount pct low-high, note, tags)
TEMPLATES = {
    "restaurant": [("Two-course dinner with wine", "A two-course dinner with a glass of the house wine.", (18, 40), (25, 50), "per person", ["food-scene"]),
                   ("Chef's tasting menu", "Five small plates from the chef, made from what is in season.", (28, 60), (20, 40), "per person", ["food-scene"]),
                   ("Brunch for two", "Two brunch plates and two coffees, served until 3 pm.", (16, 34), (20, 45), "for two", ["food-scene"])],
    "bar": [("Two cocktails for one", "Any two signature cocktails for the price of one, 6 to 9 pm.", (7, 16), (30, 50), "per drink", ["nightlife", "pub"]),
            ("Happy hour, half-price drinks", "Half-price beer, wine and cocktails until 8 pm.", (3, 8), (30, 50), "per drink", ["nightlife", "pub"])],
    "party": [("Free entry before midnight", "Skip the door fee and get a welcome drink before midnight.", (0, 10), (40, 60), "entry", ["nightlife", "nightclub"]),
              ("Guest list, entry and a drink", "Say the name at the door for entry and one drink.", (8, 18), (25, 45), "entry", ["nightlife", "nightclub"]),
              ("Rooftop sunset party", "Sunset session with a DJ, welcome drink included.", (12, 24), (20, 40), "per person", ["nightlife"])],
    "tour": [("Old town walking tour", "Two hours with a local guide through the old town.", (10, 24), (25, 45), "per person", ["old-town", "historic"]),
             ("Street food tour", "Six tastings and a local guide, three hours.", (22, 45), (20, 40), "per person", ["food-scene", "old-town"]),
             ("Sunset bike tour", "Easy ride along the water with a stop for drinks.", (18, 38), (20, 40), "per person", ["old-town"])],
    "activity": [("Beginner surf lesson", "Ninety minutes with an instructor, board and wetsuit included.", (25, 55), (20, 40), "per person", ["beachfront", "attraction"]),
                 ("Padel court, one hour", "A padel court for four, rackets and balls included.", (14, 30), (25, 45), "per court", ["attraction"]),
                 ("Kayak and snorkel trip", "Half-day trip with equipment and a guide.", (30, 60), (20, 40), "per person", ["beachfront"])],
    "spa": [("Massage and sauna, 90 minutes", "A 60-minute massage plus sauna and steam room.", (35, 80), (25, 45), "per person", ["spa", "quiet"]),
            ("Hammam ritual", "Steam, scrub and mint tea in a traditional hammam.", (28, 60), (20, 40), "per person", ["spa"])],
    "hotel": [("Third night free", "Stay two nights and get the third free in a double room.", (150, 420), (25, 40), "for 3 nights", []),
              ("Weekend room with breakfast", "Friday to Sunday, breakfast for two included.", (110, 320), (20, 35), "per night", ["quiet"])],
    "car_rental": [("20% off weekend rental", "Small car from Friday to Monday, unlimited kilometres.", (60, 150), (20, 30), "per weekend", [])],
}
_last = 0.0


def is_demo_email(email: str) -> bool:
    return email.startswith(EMAIL_PREFIX) and email.endswith("@" + EMAIL_DOMAIN)


def exists() -> bool:
    with db.tx() as c:
        return c.execute("SELECT 1 FROM partners WHERE email LIKE ? LIMIT 1", (EMAIL_PREFIX + "%@" + EMAIL_DOMAIN,)).fetchone() is not None


def _price(rng: random.Random, lo: float, hi: float, pct_lo: int, pct_hi: int) -> tuple[float, float]:
    pct = rng.randint(pct_lo, pct_hi)
    ref = round(rng.uniform(max(lo, 1), hi) if hi > 0 else 0, 0)
    price = round(ref * (1 - pct / 100), 0) if ref else 0.0
    return price, ref


def _center_point(rng: random.Random, city: str) -> tuple[float, float]:
    d = catalog.BY_CODE[city]
    return round(d["lat"] + rng.uniform(-0.02, 0.02), 5), round(d["lng"] + rng.uniform(-0.025, 0.025), 5)


def _deal_in(rng: random.Random, kind: str, city: str, lat: float, lng: float, slug: str, days: tuple[int, int] = (25, 150), flash: bool = False,
             today: date | None = None) -> deals.DealIn:
    today = today or date.today()
    title, desc, (lo, hi), (pl, ph), note, tags = rng.choice(TEMPLATES[kind])
    price, ref = _price(rng, lo, hi, pl, ph)
    if ref and price >= ref:
        price = max(0.0, ref - 1)
    if flash:
        title = "Tonight only: " + title[0].lower() + title[1:]
        price = round(price * 0.85, 0)
        vfrom = vto = today
    else:
        vfrom, vto = today - timedelta(days=rng.randint(0, 3)), today + timedelta(days=rng.randint(*days))
    return deals.DealIn(
        title=title, description=desc, category=kind, dest=city, address=None, lat=lat, lng=lng, price=price,
        reference_price=ref if ref and ref > price else None, currency=CURRENCY.get(city, "USD"), price_note=note,
        valid_from=vfrom, valid_to=vto, url=f"https://example.com/demo/{slug}", terms="Demo deal: not a real offer. Subject to availability.",
        tags=tags, external_id=f"flash-{today.isoformat()}" if flash else None)


def _art(kind: str, seed: int) -> str:
    return f"/api/deals/art/{kind}/{seed}"


def _insert_deal(partner_id: int, d: deals.DealIn, photo: str) -> int:
    """Create through the normal path, approve it, and attach the drawn picture (partners normally supply https photos)."""
    did = deals.create(partner_id, d)
    deals.review(did, True)
    with db.tx() as c:
        c.execute("UPDATE deals SET photo_url = ? WHERE id = ?", (photo, did))
    return did


def seed(count: int = 124) -> dict:
    rng = random.Random(SEED)
    cities = [c for c in MAIN for _ in range(8)] + [c for c in OTHERS for _ in range(3)] + [c for c in AUSTRALIA for _ in range(3)]
    cities = [c for c in cities if c in catalog.BY_CODE][:count]
    kinds = TYPE_MIX[:]
    rng.shuffle(kinds)
    shared_hash = security.hash_password("demo-business-not-a-real-login")
    made: dict[str, int] = {}
    now = datetime.now(timezone.utc).isoformat()
    with db.tx() as c:
        have = c.execute("SELECT COUNT(*) FROM partners WHERE email LIKE ?", (EMAIL_PREFIX + "%@" + EMAIL_DOMAIN,)).fetchone()[0]
    for i in range(have, len(cities)):
        city, kind = cities[i], kinds[i % len(kinds)]
        name = f"Demo · {rng.choice(ADJ)} {rng.choice(NOUN[kind])}"
        email = f"{EMAIL_PREFIX}{city.lower()}-{i + 1:03d}@{EMAIL_DOMAIN}"
        with db.tx() as c:
            pid = c.execute("INSERT INTO partners (email, name, business_type, city, password_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                            (email, name, kind, city, shared_hash, now)).lastrowid
        lat, lng = _center_point(rng, city)
        d = _deal_in(rng, kind, city, lat, lng, f"{city.lower()}-{i + 1}")
        _insert_deal(pid, d, _art(kind, i + 1))
        made[city] = made.get(city, 0) + 1
    refresh(force=True)
    return made


def remove() -> int:
    with db.tx() as c:
        return c.execute("DELETE FROM partners WHERE email LIKE ?", (EMAIL_PREFIX + "%@" + EMAIL_DOMAIN,)).rowcount


def refresh(force: bool = False, today: date | None = None) -> int:
    """Renew expired standing deals and post today's flash deals. Safe to call often: once an hour unless forced."""
    global _last
    if not force and time.time() - _last < 3600:
        return 0
    _last = time.time()
    today = today or date.today()
    made = 0
    with db.tx() as c:
        partners = c.execute("SELECT * FROM partners WHERE email LIKE ? AND status = 'active'", (EMAIL_PREFIX + "%@" + EMAIL_DOMAIN,)).fetchall()
        live = {r["partner_id"] for r in c.execute("SELECT DISTINCT partner_id FROM deals WHERE status = 'approved' AND valid_to >= ? AND external_id IS NULL",
                                                      (today.isoformat(),)).fetchall()}
        flashed = {r["partner_id"] for r in c.execute("SELECT partner_id FROM deals WHERE external_id = ?", (f"flash-{today.isoformat()}",)).fetchall()}
    rng = random.Random(f"{SEED}-{today.isoformat()}")
    flash_ids = {p["id"] for p in rng.sample(list(partners), k=min(30, len(partners)))}
    for p in partners:
        kind, city = p["business_type"], p["city"]
        prng = random.Random(f"{SEED}-{p['id']}-{today.isoformat()}")
        lat, lng = _center_point(prng, city)
        if p["id"] not in live:
            _insert_deal(p["id"], _deal_in(prng, kind, city, lat, lng, f"{city.lower()}-{p['id']}-r", today=today), _art(kind, p["id"] + 500))
            made += 1
        if p["id"] in flash_ids and p["id"] not in flashed:
            _insert_deal(p["id"], _deal_in(prng, kind, city, lat, lng, f"{city.lower()}-{p['id']}-f", flash=True, today=today), _art(kind, p["id"] + 900))
            made += 1
    return made


# ---------------------------------------------------------------- pictures

_ART = {  # category -> (emoji, hue)
    "restaurant": ("🍽️", 24), "bar": ("🍸", 285), "party": ("🪩", 320), "tour": ("🧭", 200), "activity": ("🏄", 175),
    "spa": ("💆", 150), "hotel": ("🛏️", 225), "car_rental": ("🚗", 10), "flight": ("✈️", 205),
}


def art_svg(kind: str, seed: int) -> str:
    """A colourful illustration for a demo deal, from the category and a number. No text from users, no scripts."""
    emoji, base = _ART.get(kind, ("🏷️", 200))
    r = random.Random(seed)
    h1, h2 = (base + r.randrange(-25, 25)) % 360, (base + 50 + r.randrange(-25, 25)) % 360
    circles = "".join(f'<circle cx="{r.randrange(0, 400)}" cy="{r.randrange(0, 240)}" r="{r.randrange(18, 70)}" fill="white" opacity="{r.uniform(0.05, 0.16):.2f}"/>'
                      for _ in range(7))
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 240" width="400" height="240" role="img" aria-label="Illustration">'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="hsl({h1} 70% 45%)"/>'
        f'<stop offset="1" stop-color="hsl({h2} 70% 22%)"/></linearGradient></defs>'
        f'<rect width="400" height="240" fill="url(#g)"/>{circles}'
        f'<text x="200" y="146" font-size="92" text-anchor="middle">{emoji}</text></svg>'
    )
