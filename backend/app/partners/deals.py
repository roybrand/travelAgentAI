"""Partner deals: validation, storage, moderation and the (payment-blind) ranking.

Two promises are enforced in code, not just in the docs:
1. A deal is shown to travelers only after a person approves it, and editing an approved deal sends it back
   for review (unless the content is identical).
2. Ranking looks only at how well a deal matches the traveler (interests, distance, real discount).
   Nothing about who the partner is or what they pay can raise a deal. `rank_deals` has no such input.
"""
import hashlib
import json
import math
import re
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.live import catalog, osm
from app.live.geo import haversine_m
from app.partners import db

# category -> (label, interest/place-type tags a deal of that kind matches by default)
CATEGORIES: dict[str, tuple[str, list[str]]] = {
    "hotel": ("Stay", []),
    "restaurant": ("Restaurant", ["food-scene", "restaurant"]),
    "bar": ("Bar or pub", ["nightlife", "pub"]),
    "party": ("Party or club", ["nightlife", "nightclub"]),
    "tour": ("Tour", ["old-town", "historic"]),
    "activity": ("Activity", ["attraction"]),
    "spa": ("Spa", ["spa"]),
    "car_rental": ("Car rental", []),
    "flight": ("Flight", []),
}
NO_LOCATION = {"flight"}  # everything else is a place you can walk to, so it needs coordinates
INTEREST_TAGS = {"beachfront", "nightlife", "food-scene", "old-town", "spa", "quiet", "pet-friendly"}
ALLOWED_TAGS = INTEREST_TAGS | set(osm.PLACE_TYPES)
MAX_DISCOUNT_PCT = 90
MAX_WINDOW_DAYS = 366
MAX_CITY_DISTANCE_M = 40_000
Category = Literal["hotel", "restaurant", "bar", "party", "tour", "activity", "spa", "car_rental", "flight"]

_HTTPS = re.compile(r"^https://[^\s]{4,480}$")


def _today() -> date:
    return date.today()


class DealIn(BaseModel):
    """What a business submits. Validated hard, because this text is shown to the public."""
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=5, max_length=90)
    description: str = Field(min_length=10, max_length=600)
    category: Category
    dest: str = Field(min_length=2, max_length=40)
    address: str | None = Field(default=None, max_length=160)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    price: float = Field(ge=0, le=100_000)
    reference_price: float | None = Field(default=None, gt=0, le=100_000)
    currency: Literal["GBP", "EUR", "USD"] = "GBP"
    price_note: str | None = Field(default=None, max_length=40)
    valid_from: date | None = None
    valid_to: date
    stock: int | None = Field(default=None, ge=1, le=100_000)
    url: str
    terms: str = Field(min_length=10, max_length=800)
    photo_url: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=6)
    external_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def check(self):
        dest = catalog.resolve(self.dest)
        if not dest:
            raise ValueError("Choose one of the destinations from the list.")
        self.dest = dest["code"]
        today = _today()
        if self.valid_from is None:
            self.valid_from = today
        if self.valid_to < today:
            raise ValueError("The end date is in the past.")
        if self.valid_to < self.valid_from:
            raise ValueError("The end date must not be before the start date.")
        if (self.valid_to - self.valid_from).days > MAX_WINDOW_DAYS:
            raise ValueError("A deal can run for at most a year. Please renew it later.")
        if self.reference_price is not None:
            if self.reference_price <= self.price:
                raise ValueError("The usual price must be higher than the deal price, or leave it blank.")
            if discount_pct(self.price, self.reference_price) > MAX_DISCOUNT_PCT:
                raise ValueError(f"Discounts above {MAX_DISCOUNT_PCT}% look like a mistake. Please check the prices.")
        if not _HTTPS.match(self.url):
            raise ValueError("The booking link must be a full https:// address.")
        if self.photo_url and not _HTTPS.match(self.photo_url):
            raise ValueError("The photo link must be a full https:// address.")
        unknown = [t for t in self.tags if t not in ALLOWED_TAGS]
        if unknown:
            raise ValueError(f"Unknown tag: {unknown[0]}")
        if self.category not in NO_LOCATION:
            if self.lat is None or self.lng is None:
                raise ValueError("Add the location of the business so travelers can find it on the map.")
            if haversine_m(self.lat, self.lng, dest["lat"], dest["lng"]) > MAX_CITY_DISTANCE_M:
                raise ValueError(f"That location is more than 40 km from {dest['city']}. Check the coordinates or the destination.")
        return self


def discount_pct(price: float, reference: float | None) -> int:
    if not reference or reference <= 0 or price >= reference:
        return 0
    return round((1 - price / reference) * 100)


def content_hash(deal: DealIn) -> str:
    body = deal.model_dump(mode="json", exclude={"external_id"})
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


# ---------------------------------------------------------------- shaping rows

def _shape(row, today: date, for_owner: bool = False) -> dict:
    valid_to = date.fromisoformat(row["valid_to"])
    dest = catalog.BY_CODE.get(row["dest"], {})
    out = {
        "id": row["id"], "title": row["title"], "description": row["description"],
        "category": row["category"], "category_label": CATEGORIES[row["category"]][0],
        "dest": row["dest"], "city": dest.get("city", row["dest"]),
        "address": row["address"], "lat": row["lat"], "lng": row["lng"],
        "price": row["price"], "reference_price": row["reference_price"], "currency": row["currency"],
        "price_note": row["price_note"], "discount_pct": discount_pct(row["price"], row["reference_price"]),
        "valid_from": row["valid_from"], "valid_to": row["valid_to"], "days_left": (valid_to - today).days,
        "stock": row["stock"], "url": row["url"], "terms": row["terms"], "photo_url": row["photo_url"],
        "tags": json.loads(row["tags"]), "partner_name": row["partner_name"], "partner": True,
    }
    if for_owner:
        out.update(
            status=row["status"], paused=bool(row["paused"]), reject_reason=row["reject_reason"],
            impressions=row["impressions"], clicks=row["clicks"], external_id=row["external_id"],
            created_at=row["created_at"],
        )
    return out


_SELECT = "SELECT d.*, p.name AS partner_name, p.email AS partner_email FROM deals d JOIN partners p ON p.id = d.partner_id"
_LIVE = "d.status = 'approved' AND d.paused = 0 AND p.status = 'active' AND d.valid_to >= ? AND d.valid_from <= ?"


# ---------------------------------------------------------------- partner writes

def _values(deal: DealIn) -> dict:
    return {
        "title": deal.title, "description": deal.description, "category": deal.category, "dest": deal.dest,
        "address": deal.address, "lat": deal.lat, "lng": deal.lng, "price": deal.price,
        "reference_price": deal.reference_price, "currency": deal.currency, "price_note": deal.price_note,
        "valid_from": deal.valid_from.isoformat(), "valid_to": deal.valid_to.isoformat(), "stock": deal.stock,
        "url": deal.url, "terms": deal.terms, "photo_url": deal.photo_url,
        "tags": json.dumps(deal.tags), "content_hash": content_hash(deal),
    }


def create(partner_id: int, deal: DealIn) -> int:
    v = _values(deal)
    now = datetime.now(timezone.utc).isoformat()
    cols = ", ".join(v)
    with db.tx() as c:
        cur = c.execute(
            f"INSERT INTO deals (partner_id, external_id, status, created_at, {cols}) "
            f"VALUES (?, ?, 'pending', ?, {', '.join('?' * len(v))})",
            (partner_id, deal.external_id, now, *v.values()),
        )
        return cur.lastrowid


def update(partner_id: int, deal_id: int, deal: DealIn) -> bool:
    """Replace the content. Identical content keeps its status; any change goes back to review."""
    v = _values(deal)
    with db.tx() as c:
        row = c.execute("SELECT content_hash, status FROM deals WHERE id = ? AND partner_id = ?", (deal_id, partner_id)).fetchone()
        if not row or row["status"] == "ended":
            return False
        changed = row["content_hash"] != v["content_hash"]
        sets = ", ".join(f"{k} = ?" for k in v)
        extra = ", status = 'pending', reject_reason = NULL, reviewed_at = NULL" if changed else ""
        c.execute(f"UPDATE deals SET {sets}{extra} WHERE id = ?", (*v.values(), deal_id))
        return True


def upsert_from_feed(partner_id: int, deal: DealIn) -> tuple[int, str]:
    """Create or update by external_id (feeds send the same deal repeatedly). Returns (id, action)."""
    with db.tx() as c:
        row = c.execute("SELECT id FROM deals WHERE partner_id = ? AND external_id = ?", (partner_id, deal.external_id)).fetchone()
    if row:
        update(partner_id, row["id"], deal)
        return row["id"], "updated"
    return create(partner_id, deal), "created"


def set_paused(partner_id: int, deal_id: int, paused: bool) -> bool:
    with db.tx() as c:
        cur = c.execute("UPDATE deals SET paused = ? WHERE id = ? AND partner_id = ? AND status != 'ended'", (int(paused), deal_id, partner_id))
        return cur.rowcount > 0


def end(partner_id: int, deal_id: int) -> bool:
    with db.tx() as c:
        cur = c.execute("UPDATE deals SET status = 'ended' WHERE id = ? AND partner_id = ?", (deal_id, partner_id))
        return cur.rowcount > 0


def for_partner(partner_id: int, today: date | None = None) -> list[dict]:
    today = today or _today()
    with db.tx() as c:
        rows = c.execute(f"{_SELECT} WHERE d.partner_id = ? ORDER BY d.id DESC", (partner_id,)).fetchall()
    return [_shape(r, today, for_owner=True) for r in rows]


# ---------------------------------------------------------------- moderation

def review_flags(deal: dict, first_deal: bool) -> list[str]:
    """Things a reviewer should look at twice. Advice, not a verdict."""
    flags = []
    if first_deal:
        flags.append("First deal from this business")
    if deal["reference_price"] is None and deal["price"] > 0:
        flags.append("No usual price given, so no discount is claimed")
    if deal["discount_pct"] >= 60:
        flags.append(f"Large discount ({deal['discount_pct']}%). Check the usual price is genuine")
    if deal["price"] == 0:
        flags.append("Free offer. Check the terms")
    if not deal["photo_url"]:
        flags.append("No photo")
    return flags


def pending(today: date | None = None) -> list[dict]:
    today = today or _today()
    with db.tx() as c:
        rows = c.execute(f"{_SELECT} WHERE d.status = 'pending' ORDER BY d.id").fetchall()
        counts = {r["partner_id"]: r["n"] for r in c.execute("SELECT partner_id, COUNT(*) AS n FROM deals GROUP BY partner_id")}
    out = []
    for r in rows:
        d = _shape(r, today, for_owner=True)
        d["partner_email"] = r["partner_email"]
        d["flags"] = review_flags(d, first_deal=counts.get(r["partner_id"], 0) == 1)
        out.append(d)
    return out


def review(deal_id: int, approve: bool, reason: str | None = None) -> bool:
    now = datetime.now(timezone.utc).isoformat()
    with db.tx() as c:
        cur = c.execute(
            "UPDATE deals SET status = ?, reject_reason = ?, reviewed_at = ? WHERE id = ? AND status = 'pending'",
            ("approved" if approve else "rejected", None if approve else reason, now, deal_id),
        )
        return cur.rowcount > 0


# ---------------------------------------------------------------- public reads and tracking

def for_city(dest_code: str, start: date | None = None, end: date | None = None, today: date | None = None, limit: int = 60) -> list[dict]:
    """Approved, active deals for a destination that overlap the trip dates (or are valid today)."""
    today = today or _today()
    start, end = start or today, end or today
    with db.tx() as c:
        rows = c.execute(
            f"{_SELECT} WHERE d.dest = ? AND d.status = 'approved' AND d.paused = 0 AND p.status = 'active' "
            "AND d.valid_to >= ? AND d.valid_from <= ? ORDER BY d.id DESC LIMIT ?",
            (dest_code, start.isoformat(), end.isoformat(), limit),
        ).fetchall()
    return [_shape(r, today) for r in rows]


def near(lat: float, lng: float, radius_m: int, today: date | None = None, limit: int = 80) -> list[dict]:
    today = today or _today()
    dlat = radius_m / 111_000
    dlng = radius_m / (111_000 * max(0.2, math.cos(math.radians(lat))))
    with db.tx() as c:
        rows = c.execute(
            f"{_SELECT} WHERE {_LIVE} AND d.lat BETWEEN ? AND ? AND d.lng BETWEEN ? AND ? LIMIT ?",
            (today.isoformat(), today.isoformat(), lat - dlat, lat + dlat, lng - dlng, lng + dlng, limit),
        ).fetchall()
    return [_shape(r, today) for r in rows]


def row(deal_id: int):
    """The raw row (with the partner's name and email joined in), for internal use only -- never returned as JSON,
    since the partner's email is not public."""
    with db.tx() as c:
        return c.execute(f"{_SELECT} WHERE d.id = ?", (deal_id,)).fetchone()


def record_impressions(ids: list[int]) -> None:
    if ids:
        with db.tx() as c:
            c.execute(f"UPDATE deals SET impressions = impressions + 1 WHERE id IN ({','.join('?' * len(ids))})", ids)


def live_on(deal_id: int, day: date) -> dict | None:
    """One approved, running deal from an active partner, if it is valid on `day`; else None."""
    with db.tx() as c:
        row = c.execute(f"{_SELECT} WHERE d.id = ? AND {_LIVE}", (deal_id, day.isoformat(), day.isoformat())).fetchone()
    return _shape(row, date.today()) if row else None


def record_click(deal_id: int) -> bool:
    with db.tx() as c:
        cur = c.execute("UPDATE deals SET clicks = clicks + 1 WHERE id = ? AND status = 'approved'", (deal_id,))
        return cur.rowcount > 0


# ---------------------------------------------------------------- ranking

def deal_tags(deal: dict) -> set[str]:
    return set(deal["tags"]) | set(CATEGORIES[deal["category"]][1])


def rank_deals(deals: list[dict], interests: list[str], place_types: list[str] | None = None,
               pos: tuple[float, float] | None = None, radius_m: int = 3000) -> list[dict]:
    """Best first. Score = interest match + real discount + closeness (when a position is known).

    Deliberately blind to the partner: there is no input for who the business is or whether it pays.
    Each result gets `match` (the tags that matched) and `why` (plain-language reasons).
    """
    wanted = set(interests) | set(place_types or [])
    out = []
    for d in deals:
        hits = sorted(deal_tags(d) & wanted)
        score, why = 1.0 + 0.4 * min(2, len(hits)), []
        if hits:
            why.append("Matches what you like")
        if d["discount_pct"] >= 10:
            score += min(0.5, d["discount_pct"] / 100)
            why.append(f"{d['discount_pct']}% below the usual price")
        if pos and d.get("lat") is not None:
            dist = haversine_m(pos[0], pos[1], d["lat"], d["lng"])
            score -= 0.5 * min(1.0, dist / radius_m)
            d = {**d, "distance_m": dist}
        out.append({**d, "match": hits, "why": why, "score": round(score, 3)})
    out.sort(key=lambda x: (-x["score"], x["id"]))
    return out


def ends_within(deal: dict, days: int) -> bool:
    return 0 <= deal["days_left"] <= days
