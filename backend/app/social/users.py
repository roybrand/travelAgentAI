"""Traveler accounts: sign-up (18+ only), sessions, profiles, photos and blocks."""
import json
import re
import time
import uuid
from datetime import date, datetime, timezone

from app import config
from app.partners import db, security
from app.social import moderation, vocab

EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")
MIN_AGE = 18
_DUMMY = security.hash_password("not-a-real-password")
_PHOTO_NAME = re.compile(r"[0-9a-f]{32}\.(jpg|png|webp)")


class UserError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def photo_dir():
    d = config.db_path().parent / "people_photos"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- accounts

def register(email: str, password: str, display_name: str, birth_year: int, agreed: bool, demo: bool = False) -> dict:
    email, name = email.strip().lower(), " ".join(display_name.split())
    if not agreed:
        raise UserError("Please confirm you are 18 or older and accept the community rules.")
    if not (1900 <= birth_year <= date.today().year - MIN_AGE):
        raise UserError("Wayfinder People is for adults. You must be 18 or older.", 403)
    if not EMAIL.match(email):
        raise UserError("Enter a valid email address.")
    if not 2 <= len(name) <= 40:
        raise UserError("Your display name must be 2 to 40 characters.")
    weak = security.is_weak_password(password)
    if weak:
        raise UserError(weak)
    try:
        with db.tx() as c:
            cur = c.execute(
                "INSERT INTO users (email, display_name, password_hash, birth_year, demo, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (email, name, security.hash_password(password), birth_year, int(demo), _now()))
            return {"id": cur.lastrowid}
    except Exception as exc:
        if "UNIQUE" in str(exc):
            raise UserError("That email is already registered. Try signing in.", 409) from exc
        raise


def login(email: str, password: str) -> dict:
    with db.tx() as c:
        row = c.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    ok = security.verify_password(password, row["password_hash"] if row else _DUMMY)
    if not row or not ok:
        raise UserError("Email or password is wrong.", 401)
    if row["status"] != "active":
        raise UserError("This account has been suspended.", 403)
    return {"id": row["id"]}


def start_session(user_id: int) -> str:
    token = security.new_token()
    with db.tx() as c:
        c.execute("DELETE FROM user_sessions WHERE expires_at < ?", (time.time(),))
        c.execute("INSERT INTO user_sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                  (security.sha256(token), user_id, time.time() + security.SESSION_SECONDS))
    return token


def end_session(token: str) -> None:
    with db.tx() as c:
        c.execute("DELETE FROM user_sessions WHERE token_hash = ?", (security.sha256(token),))


def user_for_token(token: str) -> dict | None:
    with db.tx() as c:
        row = c.execute(
            "SELECT u.* FROM user_sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ? AND s.expires_at > ?",
            (security.sha256(token), time.time())).fetchone()
    return row_to_me(row) if row and row["status"] == "active" else None


def get_row(user_id: int):
    with db.tx() as c:
        return c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def photo_url(row) -> str | None:
    if row["demo"]:
        return f"/api/people/demo-avatar/{row['id']}"   # an illustration drawn from the id, never a real person's photo
    return f"/api/people/photo/{row['photo_file']}" if row["photo_file"] else None


def row_to_me(row) -> dict:
    """The full profile, for its owner only."""
    return {
        "id": row["id"], "email": row["email"], "display_name": row["display_name"], "bio": row["bio"],
        "interests": json.loads(row["interests"]), "languages": json.loads(row["languages"]), "home_city": row["home_city"],
        "photo_url": photo_url(row), "photo_status": row["photo_status"], "visible": bool(row["visible"]),
        "gender": row["gender"], "show_age": bool(row["show_age"]), "age_band": band_of(row),
        "audience_genders": json.loads(row["audience_genders"]), "audience_ages": json.loads(row["audience_ages"]),
        "status": row["status"], "under_review": bool(row["under_review"]), "created_at": row["created_at"],
    }


def band_of(row) -> str | None:
    return vocab.age_band(row["birth_year"], date.today().year)


def card(row, shared: list[str] | None = None) -> dict:
    """What OTHER people may see: display name, bio, interests, languages, an approved photo, the gender they chose to
    share, and an age band only if they chose to show it. Never the email, birth year, exact age or location."""
    approved = row["photo_status"] == "approved"
    return {
        "id": row["id"], "display_name": row["display_name"], "bio": row["bio"], "interests": json.loads(row["interests"]),
        "languages": json.loads(row["languages"]), "home_city": row["home_city"], "gender": row["gender"],
        "age_band": band_of(row) if row["show_age"] else None,
        "photo_url": photo_url(row) if approved else None, "shared": shared or [], "demo": bool(row["demo"]),
    }


def findable(row) -> bool:
    """False while a profile is auto-hidden pending moderator review (see connect.report), even if the
    person's own 'visible' setting is on. They can still sign in and use their account meanwhile."""
    return bool(row["visible"]) and not bool(row["under_review"])


def allowed(viewer, candidate) -> bool:
    """May `viewer` see and contact `candidate`? Honours the candidate's own audience limits, for example
    'only women' or 'only 25 to 34'. A viewer who has not shared the trait cannot pass a limit on it."""
    genders = json.loads(candidate["audience_genders"])
    ages = json.loads(candidate["audience_ages"])
    if genders and viewer["gender"] not in genders:
        return False
    if ages and band_of(viewer) not in ages:
        return False
    return True


def passes(candidate, want_genders: list[str], want_ages: list[str]) -> bool:
    """Does `candidate` fit a search filter? People who did not share a gender are not returned by a gender search;
    age uses the age band, which everyone has because 18+ is required to join."""
    if want_genders and candidate["gender"] not in want_genders:
        return False
    if want_ages and band_of(candidate) not in want_ages:
        return False
    return True


def update(user_id: int, display_name=None, bio=None, interests=None, languages=None, home_city=None, visible=None,
           gender="__keep__", show_age=None, audience_genders=None, audience_ages=None) -> None:
    sets, vals = [], []
    if gender != "__keep__":
        if gender not in (None, "", *vocab.GENDERS):
            raise UserError("Choose one of the options for gender, or leave it unset.", 422)
        sets.append("gender = ?")
        vals.append(gender or None)
    if show_age is not None:
        sets.append("show_age = ?")
        vals.append(int(show_age))
    if audience_genders is not None:
        sets.append("audience_genders = ?")
        vals.append(json.dumps(vocab.clean_tags(audience_genders, vocab.GENDERS)))
    if audience_ages is not None:
        sets.append("audience_ages = ?")
        vals.append(json.dumps(vocab.clean_tags(audience_ages, vocab.AGE_BANDS)))
    if display_name is not None:
        name = " ".join(display_name.split())
        if not 2 <= len(name) <= 40:
            raise UserError("Your display name must be 2 to 40 characters.")
        sets.append("display_name = ?")
        vals.append(name)
    if bio is not None:
        if len(bio) > 280:
            raise UserError("Keep your bio under 280 characters.")
        if bio.strip() and moderation.check_text(bio):
            raise UserError("That bio may break the community rules. Please reword it.", 422)
        sets.append("bio = ?")
        vals.append(bio.strip())
    if interests is not None:
        sets.append("interests = ?")
        vals.append(json.dumps(vocab.clean_tags(interests, vocab.ACTIVITIES)[:8]))
    if languages is not None:
        sets.append("languages = ?")
        vals.append(json.dumps(vocab.clean_tags(languages, vocab.LANGUAGES)[:5]))
    if home_city is not None:
        sets.append("home_city = ?")
        vals.append(home_city.strip()[:60] or None)
    if visible is not None:
        sets.append("visible = ?")
        vals.append(int(visible))
    if sets:
        with db.tx() as c:
            c.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", (*vals, user_id))


def change_password(user_id: int, current_password: str, new_password: str) -> None:
    """Change my password. Ends every session (including this one) so a stolen token stops working too;
    the caller signs in again with the new password."""
    with db.tx() as c:
        row = c.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row or not security.verify_password(current_password, row["password_hash"]):
            raise UserError("Your current password is wrong.", 401)
        weak = security.is_weak_password(new_password)
        if weak:
            raise UserError(weak)
        c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (security.hash_password(new_password), user_id))
        c.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))


def delete_account(user_id: int, password: str) -> None:
    """Remove the account and everything attached to it: messages, requests, plans, looking-for posts and the photo."""
    with db.tx() as c:
        row = c.execute("SELECT password_hash, photo_file FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row or not security.verify_password(password, row["password_hash"]):
            raise UserError("Password is wrong.", 401)
        c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    _remove_file(row["photo_file"])


# ---------------------------------------------------------------- photos

def _remove_file(name: str | None) -> None:
    if name and _PHOTO_NAME.fullmatch(name):
        (photo_dir() / name).unlink(missing_ok=True)


def set_photo(user_id: int, data_url: str) -> str:
    """Store a profile photo. Others see it only once it is approved: automatically when OpenAI moderation is
    on and passes it, otherwise after a human approves it. Returns the resulting status."""
    try:
        raw, ext = moderation.decode_photo(data_url)
    except ValueError as exc:
        raise UserError(str(exc), 422) from exc
    flagged = moderation.check_image(data_url)
    status = "rejected" if flagged else "approved" if flagged is False else "pending"
    name = f"{uuid.uuid4().hex}.{ext}"
    if status != "rejected":
        (photo_dir() / name).write_bytes(raw)
    with db.tx() as c:
        old = c.execute("SELECT photo_file FROM users WHERE id = ?", (user_id,)).fetchone()
        c.execute("UPDATE users SET photo_file = ?, photo_status = ? WHERE id = ?",
                  (name if status != "rejected" else None, status, user_id))
    _remove_file(old["photo_file"] if old else None)
    return status


def remove_photo(user_id: int) -> None:
    with db.tx() as c:
        old = c.execute("SELECT photo_file FROM users WHERE id = ?", (user_id,)).fetchone()
        c.execute("UPDATE users SET photo_file = NULL, photo_status = 'none' WHERE id = ?", (user_id,))
    _remove_file(old["photo_file"] if old else None)


def photo_path(name: str):
    if not _PHOTO_NAME.fullmatch(name):
        return None
    with db.tx() as c:
        ok = c.execute("SELECT 1 FROM users WHERE photo_file = ? AND status = 'active'", (name,)).fetchone()
    p = photo_dir() / name
    return p if ok and p.exists() else None


def pending_photos() -> list[dict]:
    with db.tx() as c:
        rows = c.execute("SELECT id, display_name, photo_file FROM users WHERE photo_status = 'pending' AND photo_file IS NOT NULL ORDER BY id").fetchall()
    return [{"user_id": r["id"], "display_name": r["display_name"], "photo_url": f"/api/people/photo/{r['photo_file']}"} for r in rows]


def review_photo(user_id: int, approve: bool) -> bool:
    with db.tx() as c:
        row = c.execute("SELECT photo_file FROM users WHERE id = ? AND photo_status = 'pending'", (user_id,)).fetchone()
        if not row:
            return False
        if approve:
            c.execute("UPDATE users SET photo_status = 'approved' WHERE id = ?", (user_id,))
        else:
            c.execute("UPDATE users SET photo_status = 'rejected', photo_file = NULL WHERE id = ?", (user_id,))
    if not approve:
        _remove_file(row["photo_file"])
    return True


# ---------------------------------------------------------------- blocks

def blocked_between(a: int, b: int) -> bool:
    with db.tx() as c:
        return bool(c.execute("SELECT 1 FROM blocks WHERE (blocker_id = ? AND blocked_id = ?) OR (blocker_id = ? AND blocked_id = ?)",
                              (a, b, b, a)).fetchone())


def block(blocker: int, target: int) -> None:
    if blocker == target:
        raise UserError("You cannot block yourself.")
    with db.tx() as c:
        c.execute("INSERT OR IGNORE INTO blocks (blocker_id, blocked_id, created_at) VALUES (?, ?, ?)", (blocker, target, _now()))


def unblock(blocker: int, target: int) -> None:
    with db.tx() as c:
        c.execute("DELETE FROM blocks WHERE blocker_id = ? AND blocked_id = ?", (blocker, target))


def blocked_by_me(user_id: int) -> list[dict]:
    with db.tx() as c:
        rows = c.execute("SELECT u.id, u.display_name FROM blocks b JOIN users u ON u.id = b.blocked_id WHERE b.blocker_id = ?", (user_id,)).fetchall()
    return [{"id": r["id"], "display_name": r["display_name"]} for r in rows]


def hidden_ids(user_id: int) -> set[int]:
    """Everyone this user must not see, and who must not see them (blocks in either direction)."""
    with db.tx() as c:
        rows = c.execute("SELECT blocker_id, blocked_id FROM blocks WHERE blocker_id = ? OR blocked_id = ?", (user_id, user_id)).fetchall()
    return {r["blocked_id"] if r["blocker_id"] == user_id else r["blocker_id"] for r in rows}
