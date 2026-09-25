"""Partner accounts, sessions and API keys."""
import re
import time
from datetime import datetime, timezone

from app.live import catalog
from app.partners import db, security

EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")
_DUMMY_HASH = security.hash_password("not-a-real-password")  # so unknown emails cost the same time as wrong passwords


class AccountError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def register(name: str, email: str, password: str, business_type: str, city: str) -> dict:
    name, email = name.strip(), email.strip().lower()
    if not 2 <= len(name) <= 80:
        raise AccountError("Business name must be 2 to 80 characters.")
    if not EMAIL.match(email):
        raise AccountError("Enter a valid email address.")
    weak = security.is_weak_password(password)
    if weak:
        raise AccountError(weak)
    dest = catalog.resolve(city)
    if not dest:
        raise AccountError("Choose your city from the list.")
    now = datetime.now(timezone.utc).isoformat()
    try:
        with db.tx() as c:
            cur = c.execute(
                "INSERT INTO partners (email, name, business_type, city, password_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (email, name, business_type, dest["code"], security.hash_password(password), now),
            )
            return {"id": cur.lastrowid, "email": email, "name": name}
    except Exception as exc:
        if db.is_unique_violation(exc):
            raise AccountError("That email is already registered. Try signing in.", 409) from exc
        raise


def login(email: str, password: str) -> dict:
    with db.tx() as c:
        row = c.execute("SELECT * FROM partners WHERE email = ?", (email.strip().lower(),)).fetchone()
    ok = security.verify_password(password, row["password_hash"] if row else _DUMMY_HASH)
    if not row or not ok:
        raise AccountError("Email or password is wrong.", 401)
    if row["status"] != "active":
        raise AccountError("This account is suspended. Contact support.", 403)
    return {"id": row["id"], "email": row["email"], "name": row["name"]}


def start_session(partner_id: int) -> str:
    token = security.new_token()
    with db.tx() as c:
        c.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))
        c.execute("INSERT INTO sessions (token_hash, partner_id, expires_at) VALUES (?, ?, ?)",
                  (security.sha256(token), partner_id, time.time() + security.SESSION_SECONDS))
    return token


def end_session(token: str) -> None:
    with db.tx() as c:
        c.execute("DELETE FROM sessions WHERE token_hash = ?", (security.sha256(token),))


def partner_for_token(token: str) -> dict | None:
    with db.tx() as c:
        row = c.execute(
            "SELECT p.* FROM sessions s JOIN partners p ON p.id = s.partner_id WHERE s.token_hash = ? AND s.expires_at > ?",
            (security.sha256(token), time.time()),
        ).fetchone()
    return _public(row) if row and row["status"] == "active" else None


def partner_for_api_key(key: str) -> dict | None:
    with db.tx() as c:
        row = c.execute("SELECT * FROM partners WHERE api_key_hash = ?", (security.sha256(key),)).fetchone()
    return _public(row) if row and row["status"] == "active" else None


def change_password(partner_id: int, current_password: str, new_password: str) -> None:
    """Change my password. Ends every session (including this one) so a stolen token stops working too;
    the caller signs in again with the new password."""
    with db.tx() as c:
        row = c.execute("SELECT password_hash FROM partners WHERE id = ?", (partner_id,)).fetchone()
        if not row or not security.verify_password(current_password, row["password_hash"]):
            raise AccountError("Your current password is wrong.", 401)
        weak = security.is_weak_password(new_password)
        if weak:
            raise AccountError(weak)
        c.execute("UPDATE partners SET password_hash = ? WHERE id = ?", (security.hash_password(new_password), partner_id))
        c.execute("DELETE FROM sessions WHERE partner_id = ?", (partner_id,))


def rotate_api_key(partner_id: int) -> str:
    """Issue a new key. The old one stops working at once. The plain key is returned only here."""
    key = security.new_api_key()
    with db.tx() as c:
        c.execute("UPDATE partners SET api_key_hash = ? WHERE id = ?", (security.sha256(key), partner_id))
    return key


def _public(row) -> dict:
    return {
        "id": row["id"], "email": row["email"], "name": row["name"], "business_type": row["business_type"],
        "city": row["city"], "status": row["status"], "has_api_key": bool(row["api_key_hash"]), "created_at": row["created_at"],
    }


# ---------------------------------------------------------------- admin

def all_partners() -> list[dict]:
    with db.tx() as c:
        rows = c.execute(
            "SELECT p.*, COUNT(d.id) AS deals, COALESCE(SUM(d.impressions), 0) AS impressions, COALESCE(SUM(d.clicks), 0) AS clicks "
            "FROM partners p LEFT JOIN deals d ON d.partner_id = p.id GROUP BY p.id ORDER BY p.id DESC"
        ).fetchall()
    return [{**_public(r), "deals": r["deals"], "impressions": r["impressions"], "clicks": r["clicks"]} for r in rows]


def set_status(partner_id: int, status: str) -> bool:
    with db.tx() as c:
        cur = c.execute("UPDATE partners SET status = ? WHERE id = ?", (status, partner_id))
        if status != "active":
            c.execute("DELETE FROM sessions WHERE partner_id = ?", (partner_id,))
        return cur.rowcount > 0
