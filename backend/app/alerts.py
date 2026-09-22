"""Alerts: the things worth interrupting someone for, worked out from where they are going and what they like.

A person's "radar" combines up to four kinds of alert:
- deal      a good partner deal on their planned trip, or inside their chosen radius, that matches their interests
- person    someone whose request matches theirs (with the profile card, so they can see who it is)
- request   someone asked to connect
- message   a new chat message

Deals work for everyone. People, requests and messages need a signed-in People account. The server only computes the list;
the browser remembers which alerts were already seen, and turns new ones into pop-ups, the bell and (if allowed) device
notifications. A public RSS feed of deals (`/api/feed/deals.xml`) carries the same deal alerts for readers and other apps.
"""
import json
import time
from datetime import date, datetime, timedelta, timezone
from xml.sax.saxutils import escape

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.live import catalog
from app.live.geo import haversine_m
from app.partners import db, deals, demo_businesses
from app.social import connect, demo_people, intents, users, vocab

router = APIRouter()

HOT_DISCOUNT = 30      # a discount at or above this is "hot"
MAX_DEALS = 12
MAX_PEOPLE = 8


class AlertContext(BaseModel):
    dest: str | None = Field(default=None, max_length=40)
    start: date | None = None
    end: date | None = None
    interests: list[str] = Field(default_factory=list, max_length=12)
    place_types: list[str] = Field(default_factory=list, max_length=14)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    radius_m: int = Field(default=5000, ge=500, le=25000)
    min_discount: int = Field(default=20, ge=0, le=90)
    kinds: list[str] | None = None   # any of deal, person, request, message; None = all


# ---------------------------------------------------------------- deals

def _money(n: float, currency: str) -> str:
    sym = {"GBP": "£", "EUR": "€", "USD": "$"}.get(currency, "")
    return f"{sym}{n:g}" if sym else f"{n:g} {currency}"


def _ends(deal: dict) -> tuple[str | None, int | None]:
    """A friendly 'ends' phrase and hours left (to the end of the last day), or nothing when it is far off."""
    if deal["days_left"] > 2:
        return None, None
    end = datetime.combine(date.fromisoformat(deal["valid_to"]), datetime.max.time()).replace(microsecond=0)
    hours = max(0, int((end - datetime.now()).total_seconds() // 3600))
    if deal["days_left"] == 0:
        return "Ends tonight", hours
    return ("Ends tomorrow" if deal["days_left"] == 1 else "Ends in 2 days"), hours


def deal_alerts(ctx: AlertContext) -> list[dict]:
    pos = (ctx.lat, ctx.lng) if ctx.lat is not None and ctx.lng is not None else None
    dest = catalog.resolve(ctx.dest) if ctx.dest else None
    pool: dict[int, dict] = {}
    on_trip: set[int] = set()
    if dest:
        for d in deals.for_city(dest["code"], ctx.start, ctx.end, limit=80):
            pool[d["id"]] = d
            if ctx.start and ctx.end:
                on_trip.add(d["id"])
    if pos:
        for d in deals.near(pos[0], pos[1], ctx.radius_m, limit=80):
            pool.setdefault(d["id"], d)
    if not pool:
        return []
    ranked = deals.rank_deals(list(pool.values()), ctx.interests, ctx.place_types, pos, ctx.radius_m)
    out = []
    for d in ranked:
        ends, hours = _ends(d)
        matched = bool(d["match"])
        good = d["discount_pct"] >= ctx.min_discount or (ends and d["discount_pct"] >= 10) or (matched and d["discount_pct"] >= 10)
        if not good:
            continue
        hot = d["discount_pct"] >= HOT_DISCOUNT or d["days_left"] == 0
        reason = []
        if d["id"] in on_trip and dest:
            reason.append(f"During your trip to {dest['city']}")
        if d.get("distance_m") is not None:
            reason.append(f"{d['distance_m'] / 1000:.1f} km away" if d["distance_m"] >= 1000 else f"{d['distance_m']} m away")
        if matched:
            reason.append("Matches what you like")
        if ends:
            reason.append(ends)
        badge = f"−{d['discount_pct']}%" if d["discount_pct"] >= 10 else ("Tonight only" if d["days_left"] == 0 else "Deal")
        out.append({
            "id": f"deal-{d['id']}", "kind": "deal", "priority": 3 if hot else 2, "hot": hot, "score": d["score"] + (0.5 if hot else 0),
            "title": d["title"], "body": f"{_money(d['price'], d['currency'])}{' · ' + d['price_note'] if d.get('price_note') else ''} at {d['partner_name']}",
            "image": d["photo_url"], "badge": badge, "reason": reason, "hours_left": hours, "link": f"/deals?dest={d['dest']}",
            "deal": {"id": d["id"], "url": d["url"], "price": d["price"], "reference_price": d["reference_price"], "currency": d["currency"],
                     "city": d["city"], "category": d["category"], "category_label": d["category_label"], "partner_name": d["partner_name"],
                     "valid_to": d["valid_to"], "discount_pct": d["discount_pct"]},
        })
    out.sort(key=lambda a: -a["score"])
    return out[:MAX_DEALS]


# ---------------------------------------------------------------- people, requests and messages

def _connected_ids(user_id: int) -> set[int]:
    with db.tx() as c:
        rows = c.execute("SELECT from_user, to_user FROM connections WHERE from_user = ? OR to_user = ?", (user_id, user_id)).fetchall()
    return {r["to_user"] if r["from_user"] == user_id else r["from_user"] for r in rows}


def people_alerts(user_id: int) -> list[dict]:
    out, seen = [], set()
    skip = _connected_ids(user_id)
    for req in intents.mine(user_id):
        row = intents.get_mine(user_id, req["id"])
        if not row:
            continue
        for card in intents.find(user_id, row)["people"]:
            if card["id"] in seen or card["id"] in skip:
                continue
            seen.add(card["id"])
            out.append({
                "id": f"person-{card['id']}", "kind": "person", "priority": 3, "hot": True, "score": 10 + len(card["shared"]),
                "title": f"{card['display_name']} wants the same as you", "body": card["request"] or "A match for your request",
                "image": card["photo_url"], "badge": "New match", "reason": card["why"] + [card["distance"]], "hours_left": None,
                "link": f"/people?person={card['id']}", "person": card,
            })
            if len(out) >= MAX_PEOPLE:
                return out
    return out


def request_alerts(user_id: int) -> list[dict]:
    out = []
    for r in connect.overview(user_id)["incoming"]:
        p = r["person"]
        out.append({"id": f"req-{r['connection_id']}", "kind": "request", "priority": 3, "hot": True, "score": 20,
                    "title": f"{p['display_name']} wants to connect", "body": f"“{r['message']}”" if r["message"] else "Say yes to start chatting",
                    "image": p["photo_url"], "badge": "Wants to meet", "reason": [], "hours_left": None,
                    "link": "/people?tab=inbox", "person": p, "connection_id": r["connection_id"]})
    return out


def message_alerts(user_id: int) -> list[dict]:
    out = []
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    for chat in connect.overview(user_id)["chats"]:
        last = chat["last"]
        if not last or last["mine"] or last["at"] < since:
            continue
        with db.tx() as c:
            mid = c.execute("SELECT id FROM messages WHERE connection_id = ? ORDER BY id DESC LIMIT 1", (chat["connection_id"],)).fetchone()["id"]
        p = chat["person"]
        out.append({"id": f"msg-{chat['connection_id']}-{mid}", "kind": "message", "priority": 3, "hot": True, "score": 15,
                    "title": f"New message from {p['display_name']}", "body": last["body"], "image": p["photo_url"], "badge": "New message",
                    "reason": [], "hours_left": None, "link": f"/people?tab=inbox&chat={chat['connection_id']}", "person": p,
                    "connection_id": chat["connection_id"]})
    return out


# ---------------------------------------------------------------- putting it together

def compute(ctx: AlertContext, user: dict | None = None) -> list[dict]:
    """All alerts for this context, best first. Keeps the demo pools fresh (does nothing if there are none)."""
    try:
        demo_businesses.refresh()
        demo_people.refresh_pool()
    except Exception:
        pass
    kinds = set(ctx.kinds) if ctx.kinds is not None else {"deal", "person", "request", "message"}
    alerts: list[dict] = []
    if "deal" in kinds:
        alerts += deal_alerts(ctx)
    if user:
        if "message" in kinds:
            alerts += message_alerts(user["id"])
        if "request" in kinds:
            alerts += request_alerts(user["id"])
        if "person" in kinds:
            alerts += people_alerts(user["id"])
    alerts.sort(key=lambda a: (-a["priority"], -a["score"]))
    return alerts


@router.post("/api/alerts")
def alerts(ctx: AlertContext, authorization: str | None = Header(default=None)):
    """Deals for a planned trip or a radius, and (when signed in to People) matches, requests and messages."""
    token = (authorization or "").removeprefix("Bearer ").strip()
    user = users.user_for_token(token) if token else None
    found = compute(ctx, user)
    return {"alerts": found, "signed_in": bool(user), "generated_at": datetime.now(timezone.utc).isoformat(),
            "counts": {k: sum(1 for a in found if a["kind"] == k) for k in ("deal", "person", "request", "message")}}


# ---------------------------------------------------------------- RSS

def rss(dest_code: str, interests: list[str], min_discount: int, base: str) -> str:
    dest = catalog.BY_CODE[dest_code]
    items = deal_alerts(AlertContext(dest=dest_code, interests=interests, min_discount=min_discount))
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    body = []
    for a in items:
        d = a["deal"]
        desc = f"{a['badge']} · {a['body']}. " + " · ".join(a["reason"]) + f". {d['category_label']} in {d['city']}, valid until {d['valid_to']}."
        body.append(
            f"<item><title>{escape(a['title'] + ' (' + a['badge'] + ')')}</title><link>{escape(base + a['link'])}</link>"
            f"<guid isPermaLink=\"false\">wayfinder-{escape(a['id'])}</guid><pubDate>{now}</pubDate>"
            f"<category>{escape(d['category_label'])}</category><description>{escape(desc)}</description></item>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        f"<title>Wayfinder deals in {escape(dest['city'])}</title><link>{escape(base)}/deals?dest={escape(dest_code)}</link>"
        f"<description>Good partner deals in {escape(dest['city'])}, best matches first. Set by the businesses, reviewed by Wayfinder, never ranked by payment.</description>"
        f"<language>en</language><lastBuildDate>{now}</lastBuildDate>{''.join(body)}</channel></rss>")


@router.get("/api/feed/deals.xml")
def deals_feed(request: Request, dest: str, interests: str = "", min_discount: int = 15):
    """A public RSS feed of good partner deals for a city, for feed readers and other apps."""
    city = catalog.resolve(dest)
    if not city:
        raise HTTPException(status_code=404, detail="Unknown destination.")
    try:
        demo_businesses.refresh()
    except Exception:
        pass
    base = str(request.base_url).rstrip("/")
    xml = rss(city["code"], [i for i in interests.split(",") if i][:12], max(0, min(90, min_discount)), base)
    return Response(xml, media_type="application/rss+xml", headers={"Cache-Control": "public, max-age=300"})
