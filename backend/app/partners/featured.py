"""Featured deal placements: a partner pays to pin one of their own approved deals in a labelled "Featured"
strip for a destination, for a week. This is the ONLY thing money buys on Wayfinder -- deals.rank_deals, the
payment-blind ranking used everywhere else, never sees this table, and the Featured strip is always a
separate, clearly labelled slot, never merged into or reordering the ranked results.
"""
import re
from datetime import date, datetime, timedelta, timezone

from app.partners import db, deals, stripe_gateway

PRICE_CENTS = 1900          # $19
CURRENCY = "usd"
DAYS = 7
MAX_ACTIVE_PER_CITY = 6
_HTTPS = re.compile(r"^https://[^\s]{4,600}$")


class FeaturedError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def start_checkout(partner_id: int, deal_id: int, success_url: str, cancel_url: str) -> dict:
    """Begin payment for a week of featuring. Returns {checkout_url}; the deal is featured only once
    Stripe's webhook confirms the payment (see mark_paid)."""
    if not stripe_gateway.enabled():
        raise FeaturedError("Payments are not configured yet. Add a Stripe key to enable Featured placements.", 503)
    if not _HTTPS.match(success_url) or not _HTTPS.match(cancel_url):
        raise FeaturedError("Redirect addresses must be full https:// links.", 422)
    with db.tx() as c:
        d = c.execute("SELECT id, title, dest, status FROM deals WHERE id = ? AND partner_id = ?", (deal_id, partner_id)).fetchone()
    if not d or d["status"] != "approved":
        raise FeaturedError("Only one of your own approved deals can be featured.", 404)
    session = stripe_gateway.create_checkout_session(
        product_name=f"Featured placement: {d['title']}"[:250],
        description=f"{DAYS} days in the Featured strip for {d['dest']}. Never changes how deals are ranked.",
        amount_cents=PRICE_CENTS, currency=CURRENCY, success_url=success_url, cancel_url=cancel_url,
        metadata={"deal_id": deal_id, "partner_id": partner_id})
    with db.tx() as c:
        c.execute(
            "INSERT INTO featured_deals (deal_id, partner_id, session_id, status, amount_cents, currency, created_at) "
            "VALUES (?, ?, ?, 'pending', ?, ?, ?)",
            (deal_id, partner_id, session["id"], PRICE_CENTS, CURRENCY, _now().isoformat()))
    return {"checkout_url": session["url"]}


def mark_paid(session_id: str, now: datetime | None = None) -> bool:
    """Confirm a checkout from Stripe's webhook. Idempotent: returns True only the first time this session
    is confirmed (a retried webhook delivery, which Stripe does, changes nothing on the second call)."""
    now = now or _now()
    with db.tx() as c:
        row = c.execute("SELECT id FROM featured_deals WHERE session_id = ? AND status = 'pending'", (session_id,)).fetchone()
        if not row:
            return False
        ends = now + timedelta(days=DAYS)
        c.execute("UPDATE featured_deals SET status = 'paid', starts_at = ?, ends_at = ? WHERE id = ?",
                  (now.isoformat(), ends.isoformat(), row["id"]))
        return True


def mine(partner_id: int) -> dict:
    """deal_id -> when it stops being featured, for this partner's currently-paid-and-active placements."""
    with db.tx() as c:
        rows = c.execute("SELECT deal_id, ends_at FROM featured_deals WHERE partner_id = ? AND status = 'paid' AND ends_at > ?",
                         (partner_id, _now().isoformat())).fetchall()
    return {r["deal_id"]: r["ends_at"] for r in rows}


def active_for_city(dest_code: str, today: date | None = None, limit: int = MAX_ACTIVE_PER_CITY) -> list[dict]:
    """Approved, currently-paid, not-expired featured deals for a destination -- for the Featured strip only.
    Never fed into deals.rank_deals."""
    today = today or date.today()
    with db.tx() as c:
        rows = c.execute(
            f"{deals._SELECT} JOIN featured_deals f ON f.deal_id = d.id "
            "WHERE f.status = 'paid' AND f.ends_at > ? AND d.status = 'approved' AND d.paused = 0 AND p.status = 'active' "
            "AND d.dest = ? AND d.valid_to >= ? ORDER BY f.ends_at LIMIT ?",
            (_now().isoformat(), dest_code, today.isoformat(), limit)).fetchall()
    return [{**deals._shape(r, today), "featured": True} for r in rows]
