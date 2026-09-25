"""Demo bookings: the booking flow end to end, with nothing reserved and nothing charged.

A traveler reviews their trip, adds traveler details, "pays" and gets a confirmation, exactly as a real booking
would go, so the whole journey can be shown. Every response says `demo: true`, and the UI labels every step.

- The server recomputes every total from the parts (flight, nights x nightly rate, activities x travelers), so the
  confirmation can never disagree with what was booked.
- Only what the trip was is stored, never who: names, email and phone stay in the traveler's browser.
- The traveler gets a manage token once; it is stored hashed and is needed to view or cancel the booking.
- Going live means swapping `confirm()` for real supplier calls (Amadeus flight orders, hotel bookings) and
  Stripe Checkout, which the partner side already uses. See docs/06-go-live-and-partnerships.md.
"""
import json
import secrets
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from app.partners import activity, db, deals, security

router = APIRouter()

_REF_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I, so a reference can be read out over the phone
_PNR_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ"


class FlightIn(BaseModel):
    airline: str = Field(default="", max_length=60)
    depart_time: str | None = Field(default=None, max_length=5)
    stops: int = Field(default=0, ge=0, le=5)
    total_price: float = Field(ge=0, le=200_000)
    price_source: str = Field(default="demo", max_length=20)


class StayIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    price_per_night: float = Field(ge=0, le=50_000)
    price_source: str = Field(default="demo", max_length=20)


class ActivityIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    day: int = Field(ge=1, le=60)
    part: Literal["morning", "afternoon", "evening", "night"]
    cost: float | None = Field(default=None, ge=0, le=10_000)


class BookingIn(BaseModel):
    origin: str = Field(min_length=2, max_length=8)
    destination: str = Field(min_length=2, max_length=8)
    start_date: date
    end_date: date
    travelers: int = Field(ge=1, le=12)
    flight: FlightIn
    stay: StayIn
    activities: list[ActivityIn] = Field(default_factory=list, max_length=80)
    currency: str = Field(default="GBP", pattern=r"^[A-Z]{3}$")
    demo_acknowledged: bool

    @model_validator(mode="after")
    def check(self):
        if not self.demo_acknowledged:
            raise ValueError("Please confirm you understand this is a demo booking.")
        nights = (self.end_date - self.start_date).days
        if nights < 1 or nights > 60:
            raise ValueError("A booking needs between 1 and 60 nights.")
        if any(a.day > nights for a in self.activities):
            raise ValueError("An activity is planned on a day outside the trip.")
        return self


class CancelIn(BaseModel):
    token: str = Field(min_length=10, max_length=100)


def _code(chars: str, n: int) -> str:
    return "".join(secrets.choice(chars) for _ in range(n))


def totals(b: BookingIn) -> dict:
    nights = (b.end_date - b.start_date).days
    flight = round(b.flight.total_price, 2)
    stay = round(b.stay.price_per_night * nights, 2)
    acts = round(sum((a.cost or 0) * b.travelers for a in b.activities), 2)
    return {"nights": nights, "flight": flight, "stay": stay, "activities": acts, "total": round(flight + stay + acts, 2)}


def confirm(b: BookingIn) -> dict:
    """Create the demo booking. The one place a real supplier and payment call would go."""
    t = totals(b)
    token = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc).isoformat()
    # The booking keeps its tickets (what, when, price per person, code), so they can be changed later on their own.
    tickets = [{"name": a.name, "day": a.day, "part": a.part, "cost": a.cost, "code": f"T-{_code(_REF_CHARS, 5)}"}
               for a in b.activities if a.cost]
    with db.tx() as c:
        for _ in range(5):
            reference = f"WF-{_code(_REF_CHARS, 6)}"
            if not c.execute("SELECT 1 FROM demo_bookings WHERE reference = ?", (reference,)).fetchone():
                break
        c.execute(
            "INSERT INTO demo_bookings (reference, token_hash, origin, destination, start_date, end_date, travelers, "
            "activities, flight_total, stay_total, activities_total, total, currency, created_at, tickets) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (reference, security.sha256(token), b.origin.upper(), b.destination.upper(), b.start_date.isoformat(),
             b.end_date.isoformat(), b.travelers, len(b.activities), t["flight"], t["stay"], t["activities"], t["total"],
             b.currency, now, json.dumps(tickets)),
        )
    return {
        "demo": True, "reference": reference, "manage_token": token, "status": "confirmed", "booked_at": now,
        "currency": b.currency, "totals": t,
        "flight": {"pnr": _code(_PNR_CHARS, 6), "airline": b.flight.airline, "price_source": b.flight.price_source},
        "stay": {"confirmation": f"H{secrets.randbelow(10**8):08d}", "name": b.stay.name, "price_source": b.stay.price_source},
        "tickets": tickets,
        "free_activities": [a.name for a in b.activities if not a.cost],
    }


def _row(reference: str, token: str):
    with db.tx() as c:
        row = c.execute("SELECT * FROM demo_bookings WHERE reference = ?", (reference.upper(),)).fetchone()
    if not row or not secrets.compare_digest(row["token_hash"], security.sha256(token)):
        raise HTTPException(status_code=404, detail="No booking with that reference.")
    return row


def _view(row) -> dict:
    return {
        "demo": True, "reference": row["reference"], "status": row["status"], "booked_at": row["created_at"],
        "cancelled_at": row["cancelled_at"], "destination": row["destination"], "start_date": row["start_date"],
        "end_date": row["end_date"], "travelers": row["travelers"], "total": row["total"], "currency": row["currency"],
    }


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


class TicketsIn(BaseModel):
    token: str = Field(min_length=10, max_length=100)
    activities: list[ActivityIn] = Field(default_factory=list, max_length=80)


@router.put("/api/bookings/{reference}/activities")
def update_tickets(reference: str, body: TicketsIn):
    """Bring a booking's activity tickets in line with the day plan, without touching the flights or the stay: new
    paid activities get tickets (charged), dropped ones are refunded, moved ones are re-dated for free. Free
    activities need no ticket. The difference is worked out here, from each price per person and the travelers."""
    row = _row(reference, body.token)
    if row["status"] != "confirmed":
        raise HTTPException(status_code=409, detail="This booking is cancelled. Book again instead.")
    nights = (date.fromisoformat(row["end_date"]) - date.fromisoformat(row["start_date"])).days
    if any(a.day > nights for a in body.activities):
        raise HTTPException(status_code=422, detail="An activity is planned on a day outside the trip.")
    old = {t["name"]: t for t in json.loads(row["tickets"] or "[]")}
    new, added, moved = [], [], []
    for a in body.activities:
        if not a.cost:
            continue
        before = old.get(a.name)
        new.append({"name": a.name, "day": a.day, "part": a.part, "cost": a.cost,
                    "code": before["code"] if before else f"T-{_code(_REF_CHARS, 5)}"})
        if not before:
            added.append(a.name)
        elif (before["day"], before["part"]) != (a.day, a.part):
            moved.append(a.name)
    kept = {t["name"] for t in new}
    removed = [name for name in old if name not in kept]
    acts = round(sum(t["cost"] * row["travelers"] for t in new), 2)
    delta = round(acts - row["activities_total"], 2)
    total = round(row["flight_total"] + row["stay_total"] + acts, 2)
    with db.tx() as c:
        c.execute("UPDATE demo_bookings SET tickets = ?, activities = ?, activities_total = ?, total = ? WHERE id = ?",
                  (json.dumps(new), len(new), acts, total, row["id"]))
    if added or removed or moved:
        activity.record("booking.updated", added=len(added), removed=len(removed), moved=len(moved))
    return {
        "demo": True, "reference": row["reference"], "tickets": new, "added": added, "removed": removed, "moved": moved,
        "charged": max(delta, 0), "refunded": max(-delta, 0), "currency": row["currency"],
        "totals": {"nights": nights, "flight": row["flight_total"], "stay": row["stay_total"], "activities": acts, "total": total},
    }


@router.post("/api/bookings/checkout")
def checkout_started(request: Request):
    """A traveler opened checkout for a trip. Counted for the booking funnel only; nothing is stored about them."""
    security.limit(f"booking-checkout:{_ip(request)}", 60, 3600)
    activity.record("booking.checkout_started")
    return {"ok": True}


@router.post("/api/bookings")
def create_booking(body: BookingIn, request: Request):
    """Book the trip -- as a demo: nothing is reserved with any airline or hotel and nothing is charged. Returns a
    reference, confirmation codes and a manage token (shown once) for viewing or cancelling it."""
    security.limit(f"booking-create:{_ip(request)}", 20, 3600)
    booking = confirm(body)
    activity.record("booking.created", destination=body.destination.upper(), travelers=body.travelers)
    return booking


@router.get("/api/bookings/{reference}")
def get_booking(reference: str, token: str):
    """A demo booking's status, for whoever holds its manage token."""
    return _view(_row(reference, token))


@router.post("/api/bookings/{reference}/cancel")
def cancel_booking(reference: str, body: CancelIn):
    """Cancel a demo booking. The demo always refunds in full; a real one would follow each supplier's rules."""
    row = _row(reference, body.token)
    if row["status"] != "cancelled":
        with db.tx() as c:
            c.execute("UPDATE demo_bookings SET status = 'cancelled', cancelled_at = ? WHERE id = ?",
                      (datetime.now(timezone.utc).isoformat(), row["id"]))
        activity.record("booking.cancelled", destination=row["destination"])
    return _view(_row(reference, body.token))


# ---------------------------------------------------------------- one partner deal (the "Book now" on a deal)

class DealBookingIn(BaseModel):
    deal_id: int = Field(ge=1)
    date: date
    quantity: int = Field(ge=1, le=10)
    pay: Literal["venue", "now"] = "venue"  # at the place on arrival (the voucher holds the price), or now in the app
    demo_acknowledged: bool

    @model_validator(mode="after")
    def check(self):
        if not self.demo_acknowledged:
            raise ValueError("Please confirm you understand this is a demo booking.")
        if self.date < date.today():
            raise ValueError("Pick today or a later date.")
        return self


def _deal_view(row, deal: dict | None) -> dict:
    return {
        "demo": True, "reference": row["reference"], "status": row["status"], "date": row["day"], "quantity": row["quantity"], "pay": row["pay"],
        "total": row["total"], "currency": row["currency"], "cancelled_at": row["cancelled_at"],
        "deal": deal and {k: deal[k] for k in ("id", "title", "partner_name", "address", "category", "category_label", "price", "price_note", "lat", "lng")},
    }


@router.post("/api/bookings/deal")
def book_deal(body: DealBookingIn, request: Request):
    """Book one partner deal for a day, as a demo: nothing is reserved with the business and nothing is charged. The
    deal must be approved and valid that day; the price comes from our database (price x quantity), never the browser."""
    security.limit(f"booking-deal:{_ip(request)}", 30, 3600)
    deal = deals.live_on(body.deal_id, body.date)
    if not deal:
        raise HTTPException(status_code=409, detail="This deal isn't available on that date. Pick a day inside its dates.")
    if deal["stock"] is not None and body.quantity > deal["stock"]:
        raise HTTPException(status_code=409, detail=f"Only {deal['stock']} left, per the business.")
    token = secrets.token_urlsafe(24)
    total = round(deal["price"] * body.quantity, 2)
    with db.tx() as c:
        for _ in range(5):
            reference = f"WD-{_code(_REF_CHARS, 6)}"
            if not c.execute("SELECT 1 FROM demo_deal_bookings WHERE reference = ?", (reference,)).fetchone():
                break
        c.execute(
            "INSERT INTO demo_deal_bookings (reference, token_hash, deal_id, day, quantity, total, currency, created_at, pay) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (reference, security.sha256(token), deal["id"], body.date.isoformat(), body.quantity, total, deal["currency"],
             datetime.now(timezone.utc).isoformat(), body.pay),
        )
        row = c.execute("SELECT * FROM demo_deal_bookings WHERE reference = ?", (reference,)).fetchone()
    deals.record_click(deal["id"])
    activity.record("booking.deal_created", deal=deal["id"])
    return {**_deal_view(row, deal), "manage_token": token, "voucher": f"V-{_code(_REF_CHARS, 8)}"}


@router.post("/api/bookings/deal/{reference}/cancel")
def cancel_deal_booking(reference: str, body: CancelIn):
    """Cancel a demo deal booking, for whoever holds its manage token."""
    with db.tx() as c:
        row = c.execute("SELECT * FROM demo_deal_bookings WHERE reference = ?", (reference.upper(),)).fetchone()
        if not row or not secrets.compare_digest(row["token_hash"], security.sha256(body.token)):
            raise HTTPException(status_code=404, detail="No booking with that reference.")
        changed = row["status"] != "cancelled"
        if changed:
            c.execute("UPDATE demo_deal_bookings SET status = 'cancelled', cancelled_at = ? WHERE id = ?",
                      (datetime.now(timezone.utc).isoformat(), row["id"]))
        row = c.execute("SELECT * FROM demo_deal_bookings WHERE id = ?", (row["id"],)).fetchone()
    if changed:
        activity.record("booking.deal_cancelled", deal=row["deal_id"])
    return _deal_view(row, None)
