"""Runtime log of what happens on the partner side, written as markdown to backend/logs/partner-activity.md,
and mirrored into a queryable table (`analytics_events`) for the admin analytics dashboard.

Like the nearby log, it records what the system did, never who: no emails, no names, no coordinates. Only the
event, the partner or deal number, and the category and city code. The markdown file is generated data and
git-ignored; the same is true of the database, which lives in `backend/data/`.
"""
from datetime import date, datetime, timedelta, timezone

from app.config import ROOT
from app.partners import db

LOG_PATH = ROOT / "logs" / "partner-activity.md"

EVENTS = {
    "partner.registered": "A business created an account",
    "partner.suspended": "A moderator suspended a partner",
    "partner.reinstated": "A moderator reinstated a partner",
    "partner.api_key": "A partner created or replaced a feed API key",
    "deal.submitted": "A deal was submitted for review",
    "deal.edited": "A deal was edited (content changes go back to review)",
    "deal.approved": "A moderator approved a deal",
    "deal.rejected": "A moderator rejected a deal",
    "deal.paused": "A partner paused or resumed a deal",
    "deal.ended": "A partner ended a deal",
    "deal.feature_started": "A partner began payment to feature a deal",
    "deal.featured": "A featured-placement payment was confirmed by Stripe",
    "feed.received": "A feed request was processed",
    "user.registered": "A traveler created a People account",
    "user.deleted": "A traveler deleted their account and data",
    "user.banned": "A moderator banned a traveler after a report",
    "photo.submitted": "A traveler uploaded a profile photo (result: approved, pending or rejected)",
    "photo.approved": "A moderator approved a profile photo",
    "photo.rejected": "A moderator rejected a profile photo",
    "attend.added": "A traveler registered to a place for a day",
    "intent.created": "A traveler posted a looking-for-people request",
    "connection.requested": "A traveler asked to connect with someone",
    "connection.accepted": "A connection request was accepted and a chat opened",
    "message.sent": "A traveler sent a chat message (not counting an automated demo reply)",
    "report.filed": "A traveler reported someone",
    "report.dismissed": "A moderator dismissed a report",
    "profile.auto_hidden": "A profile was automatically hidden from search and new contact after reports, pending review",
    "checkin.created": "A traveler created a 'meet safely' check-in link to share outside the app",
    "booking.checkout_started": "A traveler opened checkout for a planned trip",
    "booking.created": "A traveler completed a demo booking (nothing reserved or charged)",
    "booking.cancelled": "A traveler cancelled a demo booking",
    "booking.updated": "A traveler updated a demo booking's activity tickets (added, refunded or moved), flights and stay untouched",
    "booking.deal_created": "A traveler booked a partner deal as a demo (nothing reserved or charged)",
    "booking.deal_cancelled": "A traveler cancelled a demo deal booking",
    "booking.deal_redeemed": "A business checked in a deal voucher at the place (marked as used)",
}


def record(event: str, **detail) -> None:
    """Append one row to the markdown log, and mirror it into analytics_events for charts. Logging must
    never break a request, so every failure here is swallowed."""
    assert event in EVENTS, event
    now = datetime.now(timezone.utc)
    text = ", ".join(f"{k} {v}" for k, v in detail.items()) or "-"
    row = f"| {now.strftime('%Y-%m-%d %H:%M')} | {event} | {text} |\n"
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not LOG_PATH.exists():
            LOG_PATH.write_text(
                "# Partner activity log\n\nGenerated at runtime by the partner portal. Event names are defined in "
                "`app/partners/activity.py`. No emails, names or coordinates are ever written here.\n\n"
                "| time (UTC) | event | detail |\n|---|---|---|\n",
                encoding="utf-8",
            )
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(row)
    except OSError:
        pass
    try:
        with db.tx() as c:
            # The local date, not the UTC one: daily_series/total_since/funnel below all bucket by
            # date.today() (local), the same convention deals.py and places.py already use for "today".
            c.execute("INSERT INTO analytics_events (event, day, created_at) VALUES (?, ?, ?)",
                      (event, date.today().isoformat(), now.isoformat()))
    except Exception:
        pass


# ---------------------------------------------------------------- analytics (reads analytics_events)

def daily_series(events: list[str], days: int = 30) -> list[dict]:
    """[{day, count}] for every day in the last `days` (including today, zero-filled), summed across the
    given events."""
    since = date.today() - timedelta(days=days - 1)
    placeholders = ",".join("?" * len(events))
    with db.tx() as c:
        rows = c.execute(
            f"SELECT day, COUNT(*) AS n FROM analytics_events WHERE event IN ({placeholders}) AND day >= ? GROUP BY day",
            (*events, since.isoformat())).fetchall()
    counts = {r["day"]: r["n"] for r in rows}
    out, d = [], since
    for _ in range(days):
        out.append({"day": d.isoformat(), "count": counts.get(d.isoformat(), 0)})
        d += timedelta(days=1)
    return out


def total_since(events: list[str], days: int) -> int:
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    placeholders = ",".join("?" * len(events))
    with db.tx() as c:
        return c.execute(f"SELECT COUNT(*) FROM analytics_events WHERE event IN ({placeholders}) AND day >= ?", (*events, since)).fetchone()[0]


def funnel(steps: list[tuple[str, list[str]]], days: int = 30) -> list[dict]:
    """steps: [(label, [event names]), ...] -> [{label, count}]. Each step is its own total of real events in
    the window, not a strict per-visitor conversion -- there is no visit-level tracking here (see doc 10)."""
    return [{"label": label, "count": total_since(ev, days)} for label, ev in steps]
