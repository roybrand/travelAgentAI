"""Runtime log of what happens on the partner side, written as markdown to backend/logs/partner-activity.md.

Like the nearby log, it records what the system did, never who: no emails, no names, no coordinates. Only the
event, the partner or deal number, and the category and city code. It is generated data, so it is git-ignored.
"""
from datetime import datetime, timezone

from app.config import ROOT

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
    "report.filed": "A traveler reported someone",
    "report.dismissed": "A moderator dismissed a report",
}


def record(event: str, **detail) -> None:
    """Append one row. Logging must never break a request."""
    assert event in EVENTS, event
    text = ", ".join(f"{k} {v}" for k, v in detail.items()) or "-"
    row = f"| {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} | {event} | {text} |\n"
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
