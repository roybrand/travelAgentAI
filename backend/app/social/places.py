"""Registering to places: "I'm going to this place on this day", and seeing who else is going.

Only place-level information is shared: which place and which day. Never where a person is right now.
Attendees are shown only to signed-in users, only if the attendee has kept their profile visible, and never across a block.
"""
import json
import re
from datetime import date, datetime, timedelta, timezone

from app.live import catalog
from app.live.geo import haversine_m
from app.partners import db
from app.social import users

PLACE_KEY = re.compile(r"^[a-z0-9:_.\-]{3,80}$")
MAX_PER_DAY = 10
MAX_CITY_DISTANCE_M = 40_000


class PlaceError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def valid_day(day: date) -> date:
    today = date.today()
    if not today <= day <= today + timedelta(days=14):
        raise PlaceError("Choose a day from today to two weeks ahead.", 422)
    return day


def attend(user_id: int, place_key: str, place_name: str, place_type: str | None, dest: str, lat: float, lng: float, day: date) -> int:
    city = catalog.resolve(dest)
    if not city:
        raise PlaceError("Unknown destination.", 422)
    if not PLACE_KEY.match(place_key) or not 2 <= len(place_name.strip()) <= 120:
        raise PlaceError("That place is not valid.", 422)
    if haversine_m(lat, lng, city["lat"], city["lng"]) > MAX_CITY_DISTANCE_M:
        raise PlaceError(f"That place is not in {city['city']}.", 422)
    valid_day(day)
    with db.tx() as c:
        n = c.execute("SELECT COUNT(*) FROM attendances WHERE user_id = ? AND day = ?", (user_id, day.isoformat())).fetchone()[0]
        if n >= MAX_PER_DAY:
            raise PlaceError(f"You can register for at most {MAX_PER_DAY} places a day.", 429)
        c.execute(
            "INSERT OR IGNORE INTO attendances (user_id, place_key, place_name, place_type, dest, lat, lng, day, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, place_key, place_name.strip(), place_type, city["code"], round(lat, 5), round(lng, 5), day.isoformat(),
             datetime.now(timezone.utc).isoformat()))
        return c.execute("SELECT id FROM attendances WHERE user_id = ? AND place_key = ? AND day = ?", (user_id, place_key, day.isoformat())).fetchone()["id"]


def leave(user_id: int, attendance_id: int) -> bool:
    with db.tx() as c:
        return c.execute("DELETE FROM attendances WHERE id = ? AND user_id = ?", (attendance_id, user_id)).rowcount > 0


def mine(user_id: int) -> list[dict]:
    with db.tx() as c:
        rows = c.execute("SELECT * FROM attendances WHERE user_id = ? AND day >= ? ORDER BY day, place_name",
                         (user_id, date.today().isoformat())).fetchall()
    return [{k: r[k] for k in ("id", "place_key", "place_name", "place_type", "dest", "lat", "lng", "day")} for r in rows]


def counts(place_keys: list[str], day: date) -> dict[str, int]:
    """How many discoverable people are going. A number only, so it is safe to show without signing in."""
    keys = [k for k in place_keys if PLACE_KEY.match(k)][:60]
    if not keys:
        return {}
    with db.tx() as c:
        rows = c.execute(
            f"SELECT a.place_key, COUNT(*) AS n FROM attendances a JOIN users u ON u.id = a.user_id "
            f"WHERE a.day = ? AND u.visible = 1 AND u.status = 'active' AND a.place_key IN ({','.join('?' * len(keys))}) GROUP BY a.place_key",
            (day.isoformat(), *keys)).fetchall()
    return {r["place_key"]: r["n"] for r in rows}


def attendees(viewer_id: int, place_key: str, day: date) -> dict:
    hidden = users.hidden_ids(viewer_id)
    viewer = users.get_row(viewer_id)
    with db.tx() as c:
        rows = c.execute(
            "SELECT u.*, a.id AS attendance_id FROM attendances a JOIN users u ON u.id = a.user_id "
            "WHERE a.place_key = ? AND a.day = ? AND u.status = 'active' ORDER BY a.id", (place_key, day.isoformat())).fetchall()
    going = any(r["id"] == viewer_id for r in rows)
    people = [users.card(r) for r in rows if r["id"] != viewer_id and r["visible"] and r["id"] not in hidden and users.allowed(viewer, r)]
    return {"place_key": place_key, "day": day.isoformat(), "going": going, "people": people}


def near(viewer_id: int, lat: float, lng: float, radius_m: int, day: date, my_tags: list[str],
         want_genders: list[str] = (), want_ages: list[str] = ()) -> list[dict]:
    """Places within reach where other discoverable people are going that day, honouring the search filters and
    each person's own audience limits."""
    hidden = users.hidden_ids(viewer_id)
    viewer = users.get_row(viewer_id)
    dlat = radius_m / 111_000
    with db.tx() as c:
        rows = c.execute(
            "SELECT u.*, a.place_key, a.place_name, a.place_type, a.lat AS plat, a.lng AS plng FROM attendances a "
            "JOIN users u ON u.id = a.user_id WHERE a.day = ? AND u.status = 'active' AND u.visible = 1 AND u.id != ? "
            "AND a.lat BETWEEN ? AND ?", (day.isoformat(), viewer_id, lat - dlat, lat + dlat)).fetchall()
    places: dict[str, dict] = {}
    for r in rows:
        if r["id"] in hidden or not users.allowed(viewer, r) or not users.passes(r, list(want_genders), list(want_ages)):
            continue
        dist = haversine_m(lat, lng, r["plat"], r["plng"])
        if dist > radius_m:
            continue
        shared = sorted(set(json.loads(r["interests"])) & set(my_tags))
        p = places.setdefault(r["place_key"], {"place_key": r["place_key"], "place_name": r["place_name"], "place_type": r["place_type"],
                                               "lat": r["plat"], "lng": r["plng"], "distance_m": dist, "people": []})
        p["people"].append(users.card(r, shared))
    out = []
    for p in places.values():
        p["count"] = len(p["people"])
        p["people"].sort(key=lambda x: -len(x["shared"]))
        p["people"] = p["people"][:6]
        out.append(p)
    return sorted(out, key=lambda p: (-sum(1 for x in p["people"] if x["shared"]), p["distance_m"]))[:12]
