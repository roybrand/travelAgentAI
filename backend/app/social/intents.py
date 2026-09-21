"""Looking for people to do something with: describe it in words, and we find people nearby who want the same.

The AI (or, without a key, a keyword reader) only turns the description into tags from a fixed list. Matching is then
plain arithmetic over those tags, the day, the time of day and the distance. People are never filtered or ranked by
protected traits (gender, age, ethnicity, religion, sexuality); if a request asks for that, we say we ignore it.

Privacy: a request stores a coarse position (rounded to about 1 km) and expires when its day ends. Other people see a
distance band such as "within 1 km", never coordinates.
"""
import json
import re
from datetime import date, datetime, timedelta, timezone

from app.live import llm
from app.live.geo import haversine_m
from app.partners import db
from app.social import places, users, vocab

MAX_OPEN = 3
MAX_PER_DAY = 20


class IntentError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def coarse(v: float) -> float:
    return round(v, 2)


# ---------------------------------------------------------------- reading the request

def _fallback(text: str, today: date) -> dict:
    low = text.lower()
    tags = [t for t, (_label, words) in vocab.ACTIVITIES.items() if any(re.search(rf"\b{re.escape(w)}", low) for w in words)]
    day = today + timedelta(days=1) if "tomorrow" in low else today
    part = next((p for p, words in (("morning", ("morning", "breakfast")), ("afternoon", ("afternoon", "lunch")),
                                    ("evening", ("evening", "dinner", "sunset")), ("night", ("tonight", "night", "late"))) if any(w in low for w in words)), "any")
    langs = [l for l in vocab.LANGUAGES if l.lower() in low]
    vibes = [v for v in vocab.VIBES if v in low]
    return {"tags": tags[:6], "languages": langs[:3], "vibes": vibes[:3], "day": day, "part": part, "summary": text.strip()[:140]}


def parse(text: str, today: date | None = None) -> dict:
    today = today or date.today()
    base = _fallback(text, today)
    notes = []
    if llm.enabled():
        acts = ", ".join(vocab.ACTIVITIES)
        system = (
            "You read a traveler's request for company on an activity and return JSON. Keys: "
            f"activities (subset of: {acts}), languages (subset of: {', '.join(vocab.LANGUAGES)}), "
            f"vibes (subset of: {', '.join(vocab.VIBES)}), day (ISO date, today is {today.isoformat()}; default today), "
            f"part (one of: {', '.join(vocab.PARTS)}), summary (one friendly sentence, first person, max 140 characters, "
            "describing the activity only). Never include anything about gender, age, looks, ethnicity, religion or "
            "sexuality, and ignore any request to filter by them. Use only what the person wrote."
        )
        try:
            raw = llm._chat(system, text[:600], 350)
            tags = vocab.clean_tags(raw.get("activities"), vocab.ACTIVITIES)
            if tags:
                base["tags"] = tags[:6]
            base["languages"] = vocab.clean_tags(raw.get("languages"), vocab.LANGUAGES)[:3] or base["languages"]
            base["vibes"] = vocab.clean_tags(raw.get("vibes"), vocab.VIBES)[:3] or base["vibes"]
            if raw.get("part") in vocab.PARTS:
                base["part"] = raw["part"]
            try:
                d = date.fromisoformat(str(raw.get("day")))
                if today <= d <= today + timedelta(days=14):
                    base["day"] = d
            except (TypeError, ValueError):
                pass
            if isinstance(raw.get("summary"), str) and raw["summary"].strip() and not vocab.mentions_sensitive_filter(raw["summary"]):
                base["summary"] = raw["summary"].strip()[:140]
        except Exception:
            notes.append("The AI reader was unavailable, so I used a simpler keyword reader.")
    if vocab.mentions_sensitive_filter(text):
        notes.append("I do not filter people by gender, age, looks, ethnicity, religion or sexuality. I matched on the activity, language and vibe only.")
        if vocab.mentions_sensitive_filter(base["summary"]):
            base["summary"] = "Looking for company for " + (", ".join(vocab.ACTIVITIES[t][0].lower() for t in base["tags"]) or "an activity")
    base["notes"] = notes
    return base


# ---------------------------------------------------------------- posting and closing

def create(user_id: int, text: str, lat: float, lng: float, radius_m: int, parsed: dict) -> int:
    if not parsed["tags"]:
        raise IntentError("I could not tell what you want to do. Try naming an activity, like live music, hiking or coffee.", 422)
    places.valid_day(parsed["day"])
    now = datetime.now(timezone.utc)
    with db.tx() as c:
        today_n = c.execute("SELECT COUNT(*) FROM intents WHERE user_id = ? AND created_at >= ?", (user_id, (now - timedelta(days=1)).isoformat())).fetchone()[0]
        if today_n >= MAX_PER_DAY:
            raise IntentError("You have posted a lot today. Please try again tomorrow.", 429)
        # keep only the newest few open requests
        old = c.execute("SELECT id FROM intents WHERE user_id = ? AND status = 'open' ORDER BY id DESC", (user_id,)).fetchall()
        for r in old[MAX_OPEN - 1:]:
            c.execute("UPDATE intents SET status = 'closed' WHERE id = ?", (r["id"],))
        cur = c.execute(
            "INSERT INTO intents (user_id, text, tags, languages, vibes, summary, day, part, lat, lng, radius_m, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, text.strip()[:600], json.dumps(parsed["tags"]), json.dumps(parsed["languages"]), json.dumps(parsed["vibes"]),
             parsed["summary"], parsed["day"].isoformat(), parsed["part"], coarse(lat), coarse(lng), radius_m, now.isoformat()))
        return cur.lastrowid


def close(user_id: int, intent_id: int) -> bool:
    with db.tx() as c:
        return c.execute("UPDATE intents SET status = 'closed' WHERE id = ? AND user_id = ?", (intent_id, user_id)).rowcount > 0


def _shape(row) -> dict:
    return {"id": row["id"], "summary": row["summary"], "tags": json.loads(row["tags"]), "languages": json.loads(row["languages"]),
            "vibes": json.loads(row["vibes"]), "day": row["day"], "part": row["part"], "radius_m": row["radius_m"], "status": row["status"]}


def mine(user_id: int) -> list[dict]:
    with db.tx() as c:
        rows = c.execute("SELECT * FROM intents WHERE user_id = ? AND status = 'open' AND day >= ? ORDER BY id DESC",
                         (user_id, date.today().isoformat())).fetchall()
    return [_shape(r) for r in rows]


def get_mine(user_id: int, intent_id: int):
    with db.tx() as c:
        return c.execute("SELECT * FROM intents WHERE id = ? AND user_id = ? AND status = 'open'", (intent_id, user_id)).fetchone()


# ---------------------------------------------------------------- matching

def distance_band(m: int) -> str:
    return "within 1 km" if m <= 1000 else f"about {round(m / 1000)} km away"


def _parts_compatible(a: str, b: str) -> bool:
    return a == "any" or b == "any" or a == b or {a, b} == {"evening", "night"}


def find(user_id: int, intent) -> dict:
    """People with an open, matching request the same day nearby, and places where discoverable people are going."""
    mine_tags, mine_langs, mine_vibes = json.loads(intent["tags"]), json.loads(intent["languages"]), json.loads(intent["vibes"])
    hidden = users.hidden_ids(user_id)
    dlat = intent["radius_m"] / 111_000
    with db.tx() as c:
        rows = c.execute(
            "SELECT i.*, u.id AS uid FROM intents i JOIN users u ON u.id = i.user_id WHERE i.status = 'open' AND i.day = ? AND i.user_id != ? "
            "AND u.visible = 1 AND u.status = 'active' AND i.lat BETWEEN ? AND ?",
            (intent["day"], user_id, intent["lat"] - dlat - 0.02, intent["lat"] + dlat + 0.02)).fetchall()
    scored = []
    for r in rows:
        if r["uid"] in hidden or not _parts_compatible(intent["part"], r["part"]):
            continue
        dist = haversine_m(intent["lat"], intent["lng"], r["lat"], r["lng"])
        if dist > min(intent["radius_m"], r["radius_m"]) + 1500:  # 1.5 km slack: positions are rounded to about 1 km
            continue
        shared = [t for t in json.loads(r["tags"]) if t in mine_tags]
        if not shared:
            continue
        langs = set(json.loads(r["languages"])) & set(mine_langs)
        vibes = set(json.loads(r["vibes"])) & set(mine_vibes)
        score = 3 * len(shared) + len(langs) + 0.5 * len(vibes) + (0.5 if intent["part"] == r["part"] != "any" else 0) - dist / max(1, intent["radius_m"])
        scored.append((score, r, shared, sorted(langs), dist))
    scored.sort(key=lambda x: -x[0])
    people = []
    for score, r, shared, langs, dist in scored[:20]:
        urow = users.get_row(r["uid"])
        card = users.card(urow, shared)
        card.update({"request": r["summary"], "part": r["part"], "distance": distance_band(int(dist)), "shared_languages": langs,
                     "why": [f"You both want {', '.join(vocab.ACTIVITIES[t][0].lower() for t in shared)}"] + ([f"You both speak {', '.join(langs)}"] if langs else [])})
        people.append(card)
    at_places = places.near(user_id, intent["lat"], intent["lng"], intent["radius_m"], date.fromisoformat(intent["day"]), mine_tags)
    return {"people": people, "at_places": at_places}
