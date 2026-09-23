"""Meeting: connection requests, chat, and reports. Nobody can message anyone until the other person accepts.

Rules that protect people:
- A request needs a visible, active, unblocked person and can carry one short note.
- Chat opens only after the other person accepts. Either person can end it by blocking.
- Blocking hides each person from the other everywhere and closes the chat.
- Messages and notes are checked by moderation when a key is set, and any message can be reported.
"""
from datetime import datetime, timedelta, timezone

from app.partners import activity, db
from app.social import demo_people, moderation, push, users

MAX_REQUESTS_PER_DAY = 20
MAX_MESSAGE = 500
MAX_MESSAGES_PER_10_MIN = 60
REASONS = ["harassment", "spam or scam", "fake profile", "inappropriate photo", "unsafe behaviour", "under 18", "other"]
# A profile is auto-hidden pending review once distinct people report it, or at once for the reasons below
# (a false "under 18" or "unsafe behaviour" claim costs little to check; leaving it up costs more).
AUTO_HIDE_REPORTERS = 2
AUTO_HIDE_REASONS = {"under 18", "unsafe behaviour"}


class ConnectError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pair(c, a: int, b: int):
    return c.execute("SELECT * FROM connections WHERE (from_user = ? AND to_user = ?) OR (from_user = ? AND to_user = ?)", (a, b, b, a)).fetchone()


def request(from_id: int, to_id: int, message: str) -> dict:
    message = " ".join(message.split())[:200]
    if from_id == to_id:
        raise ConnectError("You cannot connect with yourself.")
    target = users.get_row(to_id)
    sender = users.get_row(from_id)
    if not target or target["status"] != "active" or not users.findable(target) or users.blocked_between(from_id, to_id) \
            or not users.allowed(sender, target):
        raise ConnectError("That person is not available.", 404)
    if sender["under_review"]:
        raise ConnectError("Your profile is being reviewed after a report, so you cannot send new requests right now.", 403)
    if message and moderation.check_text(message):
        raise ConnectError("That note may break the community rules. Please reword it.", 422)
    result, push_job = None, None  # push_job: (user_id, title, body), sent only after the write commits
    with db.tx() as c:
        existing = _pair(c, from_id, to_id)
        if existing:
            if existing["status"] == "pending" and existing["from_user"] == to_id:
                # They already asked you: asking back means yes.
                c.execute("UPDATE connections SET status = 'accepted', responded_at = ? WHERE id = ?", (_now(), existing["id"]))
                result = {"id": existing["id"], "status": "accepted"}
                push_job = (to_id, "Request accepted", f"{sender['display_name']} accepted your request to connect.")
            else:
                raise ConnectError({"pending": "You already sent a request. Wait for their answer.",
                                    "accepted": "You are already connected.",
                                    "declined": "That request was not accepted."}[existing["status"]], 409)
        else:
            n = c.execute("SELECT COUNT(*) FROM connections WHERE from_user = ? AND created_at >= ?", (from_id, (datetime.now(timezone.utc) - timedelta(days=1)).isoformat())).fetchone()[0]
            if n >= MAX_REQUESTS_PER_DAY:
                raise ConnectError("You have sent a lot of requests today. Please try again tomorrow.", 429)
            cur = c.execute("INSERT INTO connections (from_user, to_user, message, created_at) VALUES (?, ?, ?, ?)", (from_id, to_id, message, _now()))
            if target["demo"]:
                # A demo profile accepts at once and says hello, so the chat can be shown. The chat is labelled as automated.
                c.execute("UPDATE connections SET status = 'accepted', responded_at = ? WHERE id = ?", (_now(), cur.lastrowid))
                c.execute("INSERT INTO messages (connection_id, sender_id, body, created_at) VALUES (?, ?, ?, ?)",
                          (cur.lastrowid, to_id, demo_people.welcome(target), _now()))
                result = {"id": cur.lastrowid, "status": "accepted"}
            else:
                result = {"id": cur.lastrowid, "status": "pending"}
                push_job = (to_id, "New connection request", f"{sender['display_name']} wants to connect on Wayfinder.")
    if push_job:
        push.notify_user(*push_job, url="/people?tab=inbox")
    return result


def respond(user_id: int, connection_id: int, accept: bool) -> bool:
    with db.tx() as c:
        row = c.execute("SELECT from_user FROM connections WHERE id = ? AND to_user = ? AND status = 'pending'", (connection_id, user_id)).fetchone()
        if not row:
            return False
        c.execute("UPDATE connections SET status = ?, responded_at = ? WHERE id = ?", ("accepted" if accept else "declined", _now(), connection_id))
    if accept:
        accepter = users.get_row(user_id)
        push.notify_user(row["from_user"], "Request accepted", f"{accepter['display_name']} accepted your request to connect.", url="/people?tab=inbox")
    return True


def overview(user_id: int) -> dict:
    hidden = users.hidden_ids(user_id)
    with db.tx() as c:
        rows = c.execute("SELECT * FROM connections WHERE from_user = ? OR to_user = ? ORDER BY id DESC", (user_id, user_id)).fetchall()
        out = {"incoming": [], "outgoing": [], "chats": []}
        for r in rows:
            other = r["to_user"] if r["from_user"] == user_id else r["from_user"]
            if other in hidden:
                continue
            urow = c.execute("SELECT * FROM users WHERE id = ? AND status = 'active'", (other,)).fetchone()
            if not urow:
                continue
            card = users.card(urow)
            base = {"connection_id": r["id"], "person": card, "message": r["message"], "created_at": r["created_at"]}
            if r["status"] == "pending":
                out["incoming" if r["to_user"] == user_id else "outgoing"].append(base)
            elif r["status"] == "accepted":
                last = c.execute("SELECT body, created_at, sender_id FROM messages WHERE connection_id = ? ORDER BY id DESC LIMIT 1", (r["id"],)).fetchone()
                out["chats"].append({**base, "last": {"body": last["body"][:80], "at": last["created_at"], "mine": last["sender_id"] == user_id} if last else None})
        return out


def _open_chat(c, user_id: int, connection_id: int):
    r = c.execute("SELECT * FROM connections WHERE id = ? AND (from_user = ? OR to_user = ?) AND status = 'accepted'", (connection_id, user_id, user_id)).fetchone()
    if not r:
        raise ConnectError("That chat is not available.", 404)
    other = r["to_user"] if r["from_user"] == user_id else r["from_user"]
    if users.blocked_between(user_id, other):
        raise ConnectError("That chat is not available.", 404)
    return r, other


def messages(user_id: int, connection_id: int, after: int = 0) -> list[dict]:
    with db.tx() as c:
        _open_chat(c, user_id, connection_id)
        rows = c.execute("SELECT id, sender_id, body, created_at FROM messages WHERE connection_id = ? AND id > ? ORDER BY id LIMIT 200", (connection_id, after)).fetchall()
    return [{"id": r["id"], "mine": r["sender_id"] == user_id, "body": r["body"], "at": r["created_at"]} for r in rows]


def send(user_id: int, connection_id: int, body: str) -> dict:
    body = body.strip()
    if not body or len(body) > MAX_MESSAGE:
        raise ConnectError(f"Write a message of up to {MAX_MESSAGE} characters.", 422)
    with db.tx() as c:
        _open_chat(c, user_id, connection_id)
        recent = c.execute("SELECT COUNT(*) FROM messages WHERE sender_id = ? AND created_at >= ?", (user_id, (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat())).fetchone()[0]
        if recent >= MAX_MESSAGES_PER_10_MIN:
            raise ConnectError("You are sending messages very fast. Please slow down.", 429)
    if moderation.check_text(body):
        raise ConnectError("That message may break the community rules, so it was not sent.", 422)
    with db.tx() as c:
        _, other = _open_chat(c, user_id, connection_id)
        cur = c.execute("INSERT INTO messages (connection_id, sender_id, body, created_at) VALUES (?, ?, ?, ?)", (connection_id, user_id, body, _now()))
        other_row = c.execute("SELECT * FROM users WHERE id = ?", (other,)).fetchone()
        if other_row and other_row["demo"]:  # automated reply from a demo profile
            n = c.execute("SELECT COUNT(*) FROM messages WHERE connection_id = ? AND sender_id = ?", (connection_id, user_id)).fetchone()[0]
            c.execute("INSERT INTO messages (connection_id, sender_id, body, created_at) VALUES (?, ?, ?, ?)",
                      (connection_id, other, demo_people.reply(other_row, n), _now()))
        result = {"id": cur.lastrowid, "mine": True, "body": body, "at": _now()}
    activity.record("message.sent")
    if other_row and not other_row["demo"]:
        sender = users.get_row(user_id)
        push.notify_user(other, f"Message from {sender['display_name']}", body, url=f"/people?tab=inbox&chat={connection_id}")
    return result


# ---------------------------------------------------------------- reports (and the moderator's side)

def _recompute_review(c, target_id: int) -> None:
    """Auto-hide (or clear) a profile from being found or contacted, based on its currently open reports.
    Never overrides a ban: a banned account is already excluded everywhere by its status."""
    open_rows = c.execute("SELECT DISTINCT reporter_id, reason FROM reports WHERE target_id = ? AND status = 'open'", (target_id,)).fetchall()
    reporters = {r["reporter_id"] for r in open_rows if r["reporter_id"] is not None}
    urgent = any(r["reason"] in AUTO_HIDE_REASONS for r in open_rows)
    flag = 1 if (urgent or len(reporters) >= AUTO_HIDE_REPORTERS) else 0
    before = c.execute("SELECT under_review FROM users WHERE id = ?", (target_id,)).fetchone()
    c.execute("UPDATE users SET under_review = ? WHERE id = ? AND status != 'banned'", (flag, target_id))
    if before and not before["under_review"] and flag:
        activity.record("profile.auto_hidden")


def report(reporter: int, target: int, reason: str, detail: str, message_id: int | None) -> int:
    if reason not in REASONS:
        raise ConnectError("Choose a reason from the list.", 422)
    if reporter == target or not users.get_row(target):
        raise ConnectError("That person cannot be reported.", 404)
    with db.tx() as c:
        cur = c.execute("INSERT INTO reports (reporter_id, target_id, message_id, reason, detail, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (reporter, target, message_id, reason, detail.strip()[:500], _now()))
        _recompute_review(c, target)
        return cur.lastrowid


def open_reports() -> list[dict]:
    with db.tx() as c:
        rows = c.execute(
            "SELECT r.*, t.display_name AS target_name, t.status AS target_status, t.under_review AS target_under_review, "
            "(SELECT COUNT(*) FROM reports r2 WHERE r2.target_id = r.target_id AND r2.status = 'open') AS open_against, m.body AS message_body "
            "FROM reports r JOIN users t ON t.id = r.target_id LEFT JOIN messages m ON m.id = r.message_id WHERE r.status = 'open' ORDER BY r.id").fetchall()
    return [{"id": r["id"], "target_id": r["target_id"], "target_name": r["target_name"], "target_status": r["target_status"],
             "target_under_review": bool(r["target_under_review"]), "reason": r["reason"], "detail": r["detail"], "message": r["message_body"],
             "open_against": r["open_against"], "created_at": r["created_at"]} for r in rows]


def resolve_report(report_id: int, ban: bool) -> bool:
    with db.tx() as c:
        r = c.execute("SELECT * FROM reports WHERE id = ? AND status = 'open'", (report_id,)).fetchone()
        if not r:
            return False
        c.execute("UPDATE reports SET status = ? WHERE id = ?", ("actioned" if ban else "dismissed", report_id))
        if ban:
            c.execute("UPDATE users SET status = 'banned' WHERE id = ?", (r["target_id"],))
            c.execute("DELETE FROM user_sessions WHERE user_id = ?", (r["target_id"],))
            c.execute("UPDATE reports SET status = 'actioned' WHERE target_id = ? AND status = 'open'", (r["target_id"],))
        _recompute_review(c, r["target_id"])
    return True
