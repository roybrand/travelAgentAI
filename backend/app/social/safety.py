"""'Meet safely' check-ins: a link a person can share OUTSIDE the app (a friend, a housemate) with what they told
us about a planned meetup, so someone else knows where they are meant to be. Deliberately coarse — a place a
person typed themselves, not a coordinate — and it expires. No sign-in is needed to view a link, because the
point is a friend who may not use Wayfinder can still see it.
"""
import secrets
from datetime import datetime, timedelta, timezone

from app.partners import db
from app.social import users

MAX_ACTIVE = 5
LIFETIME_AFTER_MEETUP = timedelta(hours=12)
MAX_AHEAD = timedelta(days=14)


class SafetyError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create(user_id: int, connection_id: int | None, place_text: str, meet_at: datetime, note: str) -> dict:
    place_text = " ".join(place_text.split())[:200]
    note = " ".join(note.split())[:300]
    if len(place_text) < 3:
        raise SafetyError("Describe where you are meeting, such as a bar or square name.", 422)
    if meet_at.tzinfo is None:
        meet_at = meet_at.replace(tzinfo=timezone.utc)
    if meet_at < _now() - timedelta(hours=1) or meet_at > _now() + MAX_AHEAD:
        raise SafetyError("Choose a time from now to two weeks ahead.", 422)
    other_name, other_photo = "someone I met on Wayfinder", None
    if connection_id is not None:
        with db.tx() as c:
            row = c.execute(
                "SELECT from_user, to_user FROM connections WHERE id = ? AND status = 'accepted' AND (from_user = ? OR to_user = ?)",
                (connection_id, user_id, user_id)).fetchone()
        if not row:
            raise SafetyError("That chat was not found.", 404)
        other_id = row["to_user"] if row["from_user"] == user_id else row["from_user"]
        other = users.get_row(other_id)
        if other:
            card = users.card(other)
            other_name, other_photo = card["display_name"], card["photo_url"]
    with db.tx() as c:
        active = c.execute("SELECT COUNT(*) FROM safety_checkins WHERE user_id = ? AND revoked = 0 AND expires_at > ?",
                           (user_id, _now().isoformat())).fetchone()[0]
        if active >= MAX_ACTIVE:
            raise SafetyError(f"You already have {MAX_ACTIVE} active check-ins. End one before starting another.", 429)
        token = secrets.token_urlsafe(24)
        expires_at = meet_at + LIFETIME_AFTER_MEETUP
        cur = c.execute(
            "INSERT INTO safety_checkins (token, user_id, connection_id, other_name, other_photo_url, place_text, meet_at, note, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (token, user_id, connection_id, other_name, other_photo, place_text, meet_at.isoformat(), note, _now().isoformat(), expires_at.isoformat()))
        return _shape(c.execute("SELECT * FROM safety_checkins WHERE id = ?", (cur.lastrowid,)).fetchone())


def _shape(row) -> dict:
    return {"id": row["id"], "token": row["token"], "connection_id": row["connection_id"], "other_name": row["other_name"],
            "other_photo_url": row["other_photo_url"], "place_text": row["place_text"], "meet_at": row["meet_at"], "note": row["note"],
            "revoked": bool(row["revoked"]), "created_at": row["created_at"], "expires_at": row["expires_at"]}


def mine(user_id: int) -> list[dict]:
    with db.tx() as c:
        rows = c.execute("SELECT * FROM safety_checkins WHERE user_id = ? AND expires_at > ? AND revoked = 0 ORDER BY meet_at",
                         (user_id, _now().isoformat())).fetchall()
    return [_shape(r) for r in rows]


def end(user_id: int, checkin_id: int) -> bool:
    with db.tx() as c:
        return c.execute("UPDATE safety_checkins SET revoked = 1 WHERE id = ? AND user_id = ?", (checkin_id, user_id)).rowcount > 0


def public_view(token: str) -> dict | None:
    """What anyone with the link sees, including someone with no Wayfinder account. Never the traveler's exact
    location, email or phone -- only what they chose to write down for this check-in."""
    with db.tx() as c:
        row = c.execute(
            "SELECT s.*, u.display_name AS my_name FROM safety_checkins s JOIN users u ON u.id = s.user_id WHERE s.token = ?",
            (token,)).fetchone()
    if not row:
        return None
    return {"my_name": row["my_name"], "other_name": row["other_name"], "other_photo_url": row["other_photo_url"],
            "place_text": row["place_text"], "meet_at": row["meet_at"], "note": row["note"], "revoked": bool(row["revoked"]),
            "expired": row["expires_at"] < _now().isoformat()}
