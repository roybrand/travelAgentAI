"""Trips and deal bookings kept with a traveler's Wayfinder account, so they follow them to every device.

The app still works without an account: everything lives in the browser. Once signed in (the same account as
Wayfinder People), each device calls POST /api/account/sync with what changed on it and gets back what changed
elsewhere since it last asked. The most recent edit of a document wins. A deletion is kept as a tombstone so it
reaches the other devices too.

Traveler names typed at checkout never reach the server: they are stripped from every trip here, even if a device
sends them, so the promise "these details stay on this device" holds.
"""
import json
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.partners import db
from app.social.routes import current_user

router = APIRouter()

MAX_DOC_BYTES = 1_500_000   # one trip: the planner's result, the plan and the booking, as JSON
MAX_DOCS_PER_CALL = 50
MAX_LIVE_DOCS = 300          # per account, trips and deal bookings together
PAGE = 25                    # documents sent back per call; the device asks again while `more` is true
_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_PRIVATE_BOOKING_FIELDS = ("lead", "others")  # names, email and phone typed at checkout


class DocIn(BaseModel):
    kind: Literal["trip", "deal_booking"]
    id: str
    updated_at: str = Field(min_length=10, max_length=40)
    deleted: bool = False
    data: dict | None = None

    @field_validator("id")
    @classmethod
    def plain_id(cls, v):
        if not _ID.match(v):
            raise ValueError("Document ids are letters, digits, - and _ only.")
        return v


class SyncIn(BaseModel):
    since: int = Field(default=0, ge=0)
    docs: list[DocIn] = Field(default_factory=list, max_length=MAX_DOCS_PER_CALL)


def _strip_private(kind: str, data: dict) -> dict:
    if kind == "trip" and isinstance(data.get("booking"), dict):
        data = {**data, "booking": {k: v for k, v in data["booking"].items() if k not in _PRIVATE_BOOKING_FIELDS}}
    return data


def _out(row) -> dict:
    return {"kind": row["kind"], "id": row["doc_id"], "updated_at": row["updated_at"], "deleted": bool(row["deleted"]),
            "data": None if row["deleted"] else json.loads(row["data"])}


@router.post("/api/account/sync")
def sync(body: SyncIn, user: dict = Depends(current_user)):
    """Send what changed on this device; get back what changed on the account's other devices since `since`."""
    written = set()
    with db.tx() as c:
        seq = c.execute("SELECT COALESCE(MAX(seq), 0) FROM account_docs WHERE user_id = ?", (user["id"],)).fetchone()[0]
        live = c.execute("SELECT COUNT(*) FROM account_docs WHERE user_id = ? AND deleted = 0", (user["id"],)).fetchone()[0]
        for d in body.docs:
            if not d.deleted and d.data is None:
                raise HTTPException(status_code=422, detail=f"{d.kind} {d.id} has no data.")
            data = "{}" if d.deleted else json.dumps(_strip_private(d.kind, d.data), separators=(",", ":"))
            if len(data.encode()) > MAX_DOC_BYTES:
                raise HTTPException(status_code=413, detail=f"{d.kind} {d.id} is too large to keep with the account.")
            have = c.execute("SELECT updated_at, deleted FROM account_docs WHERE user_id = ? AND kind = ? AND doc_id = ?",
                             (user["id"], d.kind, d.id)).fetchone()
            if have and have["updated_at"] >= d.updated_at:
                continue  # the account already has this edit or a newer one; the device gets it back below
            if not have and not d.deleted and live >= MAX_LIVE_DOCS:
                raise HTTPException(status_code=409, detail=f"An account keeps up to {MAX_LIVE_DOCS} trips and bookings. Delete some old ones first.")
            seq += 1
            if have:
                c.execute("UPDATE account_docs SET data = ?, updated_at = ?, deleted = ?, seq = ? WHERE user_id = ? AND kind = ? AND doc_id = ?",
                          (data, d.updated_at, int(d.deleted), seq, user["id"], d.kind, d.id))
                live += (0 if d.deleted else 1) - (0 if have["deleted"] else 1)
            else:
                c.execute("INSERT INTO account_docs (user_id, kind, doc_id, data, updated_at, seq, deleted) VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (user["id"], d.kind, d.id, data, d.updated_at, seq, int(d.deleted)))
                live += 0 if d.deleted else 1
            written.add((d.kind, d.id, d.updated_at))
        rows = c.execute("SELECT * FROM account_docs WHERE user_id = ? AND seq > ? ORDER BY seq LIMIT ?",
                         (user["id"], body.since, PAGE + 1)).fetchall()
    more = len(rows) > PAGE
    rows = rows[:PAGE]
    changes = [_out(r) for r in rows if (r["kind"], r["doc_id"], r["updated_at"]) not in written]
    # `seq` is where the device continues from: the last row sent when there is more, else the account's latest.
    return {"seq": rows[-1]["seq"] if more else seq, "more": more, "docs": changes}
