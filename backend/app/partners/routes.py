"""HTTP API for the partner portal, moderation, the partner feed, and the public deals and events lists."""
import asyncio
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field, ValidationError

from app import config
from app.live import catalog
from app.live.http import cached, get_json
from app.partners import accounts, activity, deals, demo_businesses, featured, security, stripe_gateway
from app.suppliers import ticketmaster

router = APIRouter()

DISCLOSURE = (
    "Partner deals are set by the businesses themselves. We review each one before it appears, but we do not "
    "guarantee price or availability. They are ranked by how well they match you, never by who pays."
)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------- auth dependencies

def current_partner(authorization: str | None = Header(default=None)) -> dict:
    token = (authorization or "").removeprefix("Bearer ").strip()
    partner = accounts.partner_for_token(token) if token else None
    if not partner:
        raise HTTPException(status_code=401, detail="Please sign in again.")
    return partner


def admin_required(request: Request, x_admin_token: str | None = Header(default=None)) -> None:
    expected = config.admin_token()
    if not expected:
        raise HTTPException(status_code=503, detail="Moderation is switched off. Set ADMIN_TOKEN in backend/.env and restart.")
    if not x_admin_token or not security.same(x_admin_token, expected):
        security.limit(f"admin:{_client_ip(request)}", 10, 600)
        raise HTTPException(status_code=401, detail="Wrong admin token.")


def _raise(exc: accounts.AccountError):
    raise HTTPException(status_code=exc.status, detail=str(exc))


# ---------------------------------------------------------------- public

@router.get("/api/deals/options")
def deal_options():
    """The category, tag and currency lists for the deal form, and the public disclosure text."""
    return {
        "categories": [{"key": k, "label": v[0], "needs_location": k not in deals.NO_LOCATION} for k, v in deals.CATEGORIES.items()],
        "tags": sorted(deals.ALLOWED_TAGS), "currencies": ["GBP", "EUR", "USD"],
        "max_discount_pct": deals.MAX_DISCOUNT_PCT, "disclosure": DISCLOSURE,
        "featured_price_cents": featured.PRICE_CENTS, "featured_currency": featured.CURRENCY, "featured_days": featured.DAYS,
        "payments_enabled": stripe_gateway.enabled(),
    }


@router.get("/api/deals")
def list_deals(dest: str, start: date | None = None, end: date | None = None, interests: str = "", place_types: str = "", category: str = ""):
    """Approved partner deals for a destination, ranked by match to the traveler."""
    d = catalog.resolve(dest)
    if not d:
        raise HTTPException(status_code=404, detail="Unknown destination.")
    found = deals.for_city(d["code"], start, end)
    if category:
        found = [x for x in found if x["category"] == category]
    ranked = deals.rank_deals(found, [i for i in interests.split(",") if i], [p for p in place_types.split(",") if p])
    deals.record_impressions([x["id"] for x in ranked])
    return {"destination": d["code"], "city": d["city"], "deals": ranked, "disclosure": DISCLOSURE}


@router.get("/api/deals/featured")
def list_featured(dest: str):
    """Deals a business paid to feature this week for a destination. A separate, clearly labelled slot --
    never mixed into or reordering the payment-blind list above."""
    d = catalog.resolve(dest)
    if not d:
        raise HTTPException(status_code=404, detail="Unknown destination.")
    return {"destination": d["code"], "city": d["city"], "deals": featured.active_for_city(d["code"]),
            "disclosure": "A business paid to appear here. It never changes how the deals above are ranked."}


@router.get("/api/deals/art/{kind}/{seed}")
def deal_art(kind: str, seed: int):
    """The drawn picture used by DEMO deals: a colourful illustration for the category (not a photograph)."""
    if kind not in deals.CATEGORIES or not 0 <= seed <= 100_000:
        raise HTTPException(status_code=404, detail="Not found.")
    return Response(demo_businesses.art_svg(kind, seed), media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})


@router.get("/api/deals/business-photo/{kind}/{variant}")
def deal_business_photo(kind: str, variant: int):
    """An AI-generated photo of a generic, fictional venue for a DEMO deal's category (see
    scripts/generate_demo_business_photos.py). Not a photograph of any real business."""
    if kind not in deals.CATEGORIES or not 1 <= variant <= demo_businesses.PHOTO_VARIANTS:
        raise HTTPException(status_code=404, detail="Not found.")
    for ext, media in (("webp", "image/webp"), ("png", "image/png")):
        path = demo_businesses.business_photo_dir() / f"{kind}_{variant}.{ext}"
        if path.exists():
            return FileResponse(path, media_type=media, headers={"Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff"})
    raise HTTPException(status_code=404, detail="Not found.")


@router.get("/api/deals/preview/{deal_id}", response_class=HTMLResponse)
def deal_preview(deal_id: int):
    """A simulated business page for a DEMO deal's "Get this deal" link: a small, self-contained page for that
    fictional business, clearly labelled, since there is no real website to send anyone to."""
    row = deals.row(deal_id)
    if not row or not demo_businesses.is_demo_email(row["partner_email"]):
        raise HTTPException(status_code=404, detail="Not found.")
    return HTMLResponse(demo_businesses.preview_html(row), headers={"Cache-Control": "public, max-age=300"})


@router.post("/api/deals/{deal_id}/click")
def deal_click(deal_id: int, request: Request):
    """Count one click on a deal's booking link (shown to the business as a result)."""
    security.limit(f"click:{_client_ip(request)}", 120, 600)
    if not deals.record_click(deal_id):
        raise HTTPException(status_code=404, detail="Deal not found.")
    return {"ok": True}


@router.get("/api/events")
async def list_events(dest: str, start: date | None = None, end: date | None = None):
    """Live events near a destination during the trip (needs a free Ticketmaster key)."""
    d = catalog.resolve(dest)
    if not d:
        raise HTTPException(status_code=404, detail="Unknown destination.")
    if not ticketmaster.enabled():
        return {"enabled": False, "events": [], "detail": "Add a free TICKETMASTER_API_KEY to backend/.env to show live events."}
    start = start or date.today()
    end = end or start
    if end < start or (end - start).days > 60:
        raise HTTPException(status_code=422, detail="Choose a date range of up to 60 days.")
    try:
        events = await asyncio.wait_for(asyncio.to_thread(ticketmaster.events_for_trip, d["lat"], d["lng"], start, end), timeout=30)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Events are temporarily unavailable ({type(exc).__name__}).") from exc
    return {"enabled": True, "events": events, "attribution": "Events by Ticketmaster"}


# ---------------------------------------------------------------- partner accounts

class RegisterIn(BaseModel):
    name: str = Field(max_length=80)
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)
    business_type: deals.Category
    city: str = Field(max_length=40)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


@router.post("/api/partners/register")
def register(body: RegisterIn, request: Request):
    """Create a partner account and sign in."""
    security.limit(f"register:{_client_ip(request)}", 20, 3600)
    try:
        partner = accounts.register(body.name, body.email, body.password, body.business_type, body.city)
    except accounts.AccountError as exc:
        _raise(exc)
    activity.record("partner.registered", partner=partner["id"], type=body.business_type, city=body.city.upper())
    return {"token": accounts.start_session(partner["id"]), "partner": partner}


@router.post("/api/partners/login")
def login(body: LoginIn, request: Request):
    """Sign in a partner. Rate limited per address and, separately, per account -- so a distributed
    guessing attempt against one email from many addresses is throttled too."""
    security.limit(f"login:{_client_ip(request)}", 15, 600)
    security.limit(f"login-acct:{body.email.strip().lower()}", 8, 900)
    try:
        partner = accounts.login(body.email, body.password)
    except accounts.AccountError as exc:
        _raise(exc)
    return {"token": accounts.start_session(partner["id"]), "partner": partner}


@router.post("/api/partners/logout")
def logout(authorization: str | None = Header(default=None)):
    """End the current partner session."""
    token = (authorization or "").removeprefix("Bearer ").strip()
    if token:
        accounts.end_session(token)
    return {"ok": True}


@router.get("/api/partners/me")
def me(partner: dict = Depends(current_partner)):
    """The signed-in partner's profile, totals, and every deal with its views and clicks."""
    mine = deals.for_partner(partner["id"])
    totals = {
        "deals": len(mine),
        "live": sum(1 for d in mine if d["status"] == "approved" and not d["paused"]),
        "pending": sum(1 for d in mine if d["status"] == "pending"),
        "impressions": sum(d["impressions"] for d in mine),
        "clicks": sum(d["clicks"] for d in mine),
    }
    return {"partner": partner, "totals": totals, "deals": mine, "featured": featured.mine(partner["id"])}


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


@router.post("/api/partners/change-password")
def change_password(body: ChangePasswordIn, partner: dict = Depends(current_partner)):
    """Change my password. Ends every session, including this one -- sign in again with the new password."""
    security.limit(f"change-pw:{partner['id']}", 10, 3600)
    try:
        accounts.change_password(partner["id"], body.current_password, body.new_password)
    except accounts.AccountError as exc:
        _raise(exc)
    return {"ok": True}


@router.post("/api/partners/api-key")
def new_api_key(partner: dict = Depends(current_partner)):
    """Create or replace the feed API key. The key is shown once."""
    activity.record("partner.api_key", partner=partner["id"])
    return {"api_key": accounts.rotate_api_key(partner["id"]),
            "note": "Copy it now. It is shown only once, and any earlier key stops working."}


@router.post("/api/partners/deals")
def create_deal(body: deals.DealIn, partner: dict = Depends(current_partner)):
    """Submit a new deal. It waits for moderator review before travelers see it."""
    deal_id = deals.create(partner["id"], body)
    activity.record("deal.submitted", deal=deal_id, partner=partner["id"], category=body.category, city=body.dest)
    return {"id": deal_id, "status": "pending"}


@router.put("/api/partners/deals/{deal_id}")
def update_deal(deal_id: int, body: deals.DealIn, partner: dict = Depends(current_partner)):
    """Edit a deal. Changed content goes back to review; identical content stays live."""
    if not deals.update(partner["id"], deal_id, body):
        raise HTTPException(status_code=404, detail="Deal not found.")
    activity.record("deal.edited", deal=deal_id, partner=partner["id"])
    return {"ok": True}


class PauseIn(BaseModel):
    paused: bool


@router.post("/api/partners/deals/{deal_id}/pause")
def pause_deal(deal_id: int, body: PauseIn, partner: dict = Depends(current_partner)):
    """Pause or resume one of the partner's deals."""
    if not deals.set_paused(partner["id"], deal_id, body.paused):
        raise HTTPException(status_code=404, detail="Deal not found.")
    activity.record("deal.paused", deal=deal_id, partner=partner["id"], paused=body.paused)
    return {"ok": True}


@router.delete("/api/partners/deals/{deal_id}")
def end_deal(deal_id: int, partner: dict = Depends(current_partner)):
    """End one of the partner's deals for good."""
    if not deals.end(partner["id"], deal_id):
        raise HTTPException(status_code=404, detail="Deal not found.")
    activity.record("deal.ended", deal=deal_id, partner=partner["id"])
    return {"ok": True}


class FeatureIn(BaseModel):
    success_url: str = Field(max_length=400)
    cancel_url: str = Field(max_length=400)


@router.post("/api/partners/deals/{deal_id}/feature")
def feature_deal(deal_id: int, body: FeatureIn, partner: dict = Depends(current_partner)):
    """Start payment to pin one of my own approved deals in the Featured strip for a week. Returns a Stripe
    Checkout URL to redirect to; the placement only takes effect once the webhook confirms payment."""
    security.limit(f"feature:{partner['id']}", 20, 3600)
    try:
        result = featured.start_checkout(partner["id"], deal_id, body.success_url, body.cancel_url)
    except featured.FeaturedError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    activity.record("deal.feature_started", deal=deal_id, partner=partner["id"])
    return result


@router.post("/api/payments/stripe/webhook")
async def stripe_webhook(request: Request):
    """Stripe calls this when a Featured-placement checkout completes. The signature is verified before
    anything in the body is trusted (see stripe_gateway.verify_webhook)."""
    payload = await request.body()
    event = stripe_gateway.verify_webhook(payload, request.headers.get("stripe-signature", ""))
    if not event:
        raise HTTPException(status_code=400, detail="Invalid or unconfigured webhook signature.")
    if event.get("type") == "checkout.session.completed":
        session = event.get("data", {}).get("object", {})
        if featured.mark_paid(session.get("id", "")):
            activity.record("deal.featured", deal=session.get("metadata", {}).get("deal_id"))
    return {"received": True}


@router.get("/api/partners/geocode")
def geocode(q: str, dest: str, partner: dict = Depends(current_partner)):
    """Find coordinates for a street address, near the chosen city (OpenStreetMap Nominatim, free)."""
    security.limit(f"geocode:{partner['id']}", 30, 600)
    d = catalog.resolve(dest)
    if not d or len(q.strip()) < 4:
        raise HTTPException(status_code=422, detail="Enter a street address and choose a destination.")
    if config.offline():
        raise HTTPException(status_code=503, detail="Address search needs internet. Enter the coordinates instead.")
    box = 0.35  # about 40 km around the city centre
    params = {
        "q": q.strip(), "format": "jsonv2", "limit": 1, "bounded": 1,
        "viewbox": f"{d['lng'] - box},{d['lat'] + box},{d['lng'] + box},{d['lat'] - box}",
    }
    try:
        hits = cached(f"geo_{d['code']}_{q.strip().lower()[:80]}", 30 * 86400,
                      lambda: get_json("https://nominatim.openstreetmap.org/search", params, timeout=15))
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Address search is busy. Try again, or enter the coordinates.") from exc
    if not hits:
        raise HTTPException(status_code=404, detail=f"No match near {d['city']}. Try a fuller address or enter the coordinates.")
    return {"lat": round(float(hits[0]["lat"]), 6), "lng": round(float(hits[0]["lon"]), 6), "label": hits[0].get("display_name", "")[:160]}


# ---------------------------------------------------------------- partner feed (API key)

class FeedIn(BaseModel):
    deals: list[dict] = Field(max_length=100)


@router.post("/api/partner-feed")
def partner_feed(body: FeedIn, request: Request, x_api_key: str | None = Header(default=None)):
    """Bulk create/update deals with an API key. Each item needs a stable external_id and an explicit valid_from.
    Items go through the same validation and review as deals typed into the portal."""
    security.limit(f"feed:{_client_ip(request)}", 60, 600)
    partner = accounts.partner_for_api_key(x_api_key) if x_api_key else None
    if not partner:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key.")
    results = []
    for i, raw in enumerate(body.deals):
        try:
            item = deals.DealIn.model_validate(raw)
            if not item.external_id or not (isinstance(raw, dict) and raw.get("valid_from")):
                raise ValueError("Feed items need external_id and valid_from so repeat sends do not restart review.")
            deal_id, action = deals.upsert_from_feed(partner["id"], item)
            results.append({"index": i, "external_id": item.external_id, "id": deal_id, "result": action})
        except ValidationError as exc:
            results.append({"index": i, "result": "rejected", "errors": [str(e["msg"]).removeprefix("Value error, ") for e in exc.errors()]})
        except ValueError as exc:
            results.append({"index": i, "result": "rejected", "errors": [str(exc)]})
    activity.record("feed.received", partner=partner["id"], items=len(body.deals), accepted=sum(r["result"] != "rejected" for r in results))
    return {"results": results, "note": "New and changed deals are pending review before they appear."}


# ---------------------------------------------------------------- admin (moderation)

@router.get("/api/admin/deals", dependencies=[Depends(admin_required)])
def admin_pending():
    """Deals waiting for review, with reviewer flags."""
    return {"deals": deals.pending()}


class ReviewIn(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


@router.post("/api/admin/deals/{deal_id}/approve", dependencies=[Depends(admin_required)])
def admin_approve(deal_id: int):
    """Approve a pending deal so travelers can see it."""
    if not deals.review(deal_id, True):
        raise HTTPException(status_code=404, detail="That deal is not waiting for review.")
    activity.record("deal.approved", deal=deal_id)
    return {"ok": True}


@router.post("/api/admin/deals/{deal_id}/reject", dependencies=[Depends(admin_required)])
def admin_reject(deal_id: int, body: ReviewIn):
    """Reject a pending deal with a reason the business will see."""
    if not body.reason or len(body.reason.strip()) < 5:
        raise HTTPException(status_code=422, detail="Give the business a reason (at least 5 characters).")
    if not deals.review(deal_id, False, body.reason.strip()):
        raise HTTPException(status_code=404, detail="That deal is not waiting for review.")
    activity.record("deal.rejected", deal=deal_id)
    return {"ok": True}


@router.get("/api/admin/analytics/summary", dependencies=[Depends(admin_required)])
def admin_analytics(days: int = 30):
    """Self-hosted analytics: signups, activation and engagement, built entirely from events already in the
    activity log (see app/partners/activity.py). No vendor, no cookies, no cross-site tracking. There is no
    visit-level tracking, so this is a funnel of real actions, not a strict per-visitor conversion rate."""
    days = max(7, min(days, 90))
    kpis = {
        "people_registered": activity.total_since(["user.registered"], days),
        "partners_registered": activity.total_since(["partner.registered"], days),
        "deals_submitted": activity.total_since(["deal.submitted"], days),
        "connections_requested": activity.total_since(["connection.requested"], days),
        "messages_sent": activity.total_since(["message.sent"], days),
        "reports_filed": activity.total_since(["report.filed"], days),
        "demo_bookings": activity.total_since(["booking.created"], days),
    }
    daily = {
        "people_registered": activity.daily_series(["user.registered"], days),
        "connections_requested": activity.daily_series(["connection.requested"], days),
        "messages_sent": activity.daily_series(["message.sent"], days),
    }
    people_funnel = activity.funnel([
        ("Registered", ["user.registered"]),
        ("Posted a looking-for request", ["intent.created"]),
        ("Sent a connection request", ["connection.requested"]),
        ("Had a request accepted", ["connection.accepted"]),
        ("Sent a message", ["message.sent"]),
    ], days)
    partner_funnel = activity.funnel([
        ("Registered", ["partner.registered"]),
        ("Submitted a deal", ["deal.submitted"]),
        ("Deal approved", ["deal.approved"]),
        ("Paid to feature a deal", ["deal.featured"]),
    ], days)
    booking_funnel = activity.funnel([
        ("Opened checkout", ["booking.checkout_started"]),
        ("Booked (demo)", ["booking.created"]),
        ("Cancelled", ["booking.cancelled"]),
    ], days)
    return {"days": days, "kpis": kpis, "daily": daily, "people_funnel": people_funnel, "partner_funnel": partner_funnel,
            "booking_funnel": booking_funnel}


@router.get("/api/admin/partners", dependencies=[Depends(admin_required)])
def admin_partners():
    """Every partner with deal, view and click totals."""
    return {"partners": accounts.all_partners()}


class StatusIn(BaseModel):
    status: str = Field(pattern="^(active|suspended)$")


@router.post("/api/admin/partners/{partner_id}/status", dependencies=[Depends(admin_required)])
def admin_partner_status(partner_id: int, body: StatusIn):
    """Suspend or reinstate a partner. Suspension hides their deals and blocks sign-in."""
    if not accounts.set_status(partner_id, body.status):
        raise HTTPException(status_code=404, detail="Partner not found.")
    activity.record("partner.suspended" if body.status == "suspended" else "partner.reinstated", partner=partner_id)
    return {"ok": True}
