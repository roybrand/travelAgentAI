"""HTTP API for Wayfinder People: accounts, profiles, places, finding people, connections, chat and safety."""
import asyncio
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.partners import activity, db, security
from app.partners.routes import admin_required
from app.social import connect, intents, places, users, vocab

router = APIRouter()

COMMUNITY_RULES = [
    "You must be 18 or older.",
    "Be kind. No harassment, hate, threats, spam or scams.",
    "Use your own photo of yourself. No one else's, no nudity.",
    "Meet in public places, tell a friend, and trust your instincts. Leave if you feel unsafe.",
    "Never send money or share financial details with someone you met here.",
    "Report anyone who breaks these rules. We review every report.",
]


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def current_user(authorization: str | None = Header(default=None)) -> dict:
    token = (authorization or "").removeprefix("Bearer ").strip()
    user = users.user_for_token(token) if token else None
    if not user:
        raise HTTPException(status_code=401, detail="Please sign in again.")
    return user


def _fail(exc: Exception):
    raise HTTPException(status_code=getattr(exc, "status", 400), detail=str(exc)) from exc


def _day(value: date | None) -> date:
    try:
        return places.valid_day(value or date.today())
    except places.PlaceError as exc:
        _fail(exc)


# ---------------------------------------------------------------- vocabulary and rules (public)

@router.get("/api/people/options")
def options():
    """Activity, language and vibe lists for profiles and requests, and the community rules."""
    return {"activities": [{"key": k, "label": v[0]} for k, v in vocab.ACTIVITIES.items()], "languages": vocab.LANGUAGES,
            "vibes": vocab.VIBES, "rules": COMMUNITY_RULES, "report_reasons": connect.REASONS, "min_age": users.MIN_AGE}


@router.get("/api/people/counts")
def counts(keys: str, day: date | None = None):
    """How many discoverable people are going to each place on a day. Numbers only, so no sign-in is needed."""
    return {"day": _day(day).isoformat(), "counts": places.counts([k for k in keys.split(",") if k], _day(day))}


# ---------------------------------------------------------------- accounts

class SignUp(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)
    display_name: str = Field(max_length=60)
    birth_year: int
    agreed: bool


class SignIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


@router.post("/api/people/register")
def register(body: SignUp, request: Request):
    """Create a traveler account. Adults only: the person confirms they are 18 or older and accepts the rules."""
    security.limit(f"people-register:{_ip(request)}", 20, 3600)
    try:
        user = users.register(body.email, body.password, body.display_name, body.birth_year, body.agreed)
    except users.UserError as exc:
        _fail(exc)
    activity.record("user.registered")
    return {"token": users.start_session(user["id"]), "me": users.row_to_me(users.get_row(user["id"]))}


@router.post("/api/people/login")
def login(body: SignIn, request: Request):
    """Sign in a traveler. Rate limited."""
    security.limit(f"people-login:{_ip(request)}", 15, 600)
    try:
        user = users.login(body.email, body.password)
    except users.UserError as exc:
        _fail(exc)
    return {"token": users.start_session(user["id"]), "me": users.row_to_me(users.get_row(user["id"]))}


@router.post("/api/people/logout")
def logout(authorization: str | None = Header(default=None)):
    """End the current session."""
    token = (authorization or "").removeprefix("Bearer ").strip()
    if token:
        users.end_session(token)
    return {"ok": True}


@router.get("/api/people/me")
def me(user: dict = Depends(current_user)):
    """My profile, my plans, my open requests and the people I have blocked."""
    return {"me": user, "plans": places.mine(user["id"]), "requests": intents.mine(user["id"]), "blocked": users.blocked_by_me(user["id"])}


class ProfileIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=60)
    bio: str | None = Field(default=None, max_length=400)
    interests: list[str] | None = None
    languages: list[str] | None = None
    home_city: str | None = Field(default=None, max_length=60)
    visible: bool | None = None


@router.patch("/api/people/me")
def update_me(body: ProfileIn, user: dict = Depends(current_user)):
    """Edit my profile, or hide it from everyone with visible=false."""
    try:
        users.update(user["id"], body.display_name, body.bio, body.interests, body.languages, body.home_city, body.visible)
    except users.UserError as exc:
        _fail(exc)
    return {"me": users.row_to_me(users.get_row(user["id"]))}


class PhotoIn(BaseModel):
    image: str = Field(max_length=700_000)


@router.post("/api/people/me/photo")
def upload_photo(body: PhotoIn, request: Request, user: dict = Depends(current_user)):
    """Upload a profile photo (a small JPEG, PNG or WebP). Others see it only after it is approved."""
    security.limit(f"people-photo:{user['id']}", 10, 86400)
    try:
        status = users.set_photo(user["id"], body.image)
    except users.UserError as exc:
        _fail(exc)
    activity.record("photo.submitted", result=status)
    return {"status": status, "me": users.row_to_me(users.get_row(user["id"]))}


@router.delete("/api/people/me/photo")
def delete_photo(user: dict = Depends(current_user)):
    """Remove my profile photo."""
    users.remove_photo(user["id"])
    return {"ok": True}


@router.get("/api/people/photo/{name}")
def photo(name: str):
    """A profile photo. The address is a random 128-bit name that is only shown to people who may see the photo."""
    path = users.photo_path(name)
    if not path:
        raise HTTPException(status_code=404, detail="Not found.")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})


class DeleteIn(BaseModel):
    password: str = Field(max_length=200)


@router.post("/api/people/me/delete")
def delete_me(body: DeleteIn, user: dict = Depends(current_user)):
    """Delete my account and everything attached to it: messages, requests, plans and photo."""
    try:
        users.delete_account(user["id"], body.password)
    except users.UserError as exc:
        _fail(exc)
    activity.record("user.deleted")
    return {"ok": True}


# ---------------------------------------------------------------- places

class AttendIn(BaseModel):
    place_key: str = Field(max_length=80)
    place_name: str = Field(max_length=120)
    place_type: str | None = Field(default=None, max_length=30)
    dest: str = Field(max_length=40)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    day: date | None = None


@router.post("/api/people/attend")
def attend(body: AttendIn, user: dict = Depends(current_user)):
    """Register to a place for a day: 'I am going'. Others going there can see my profile if it is visible."""
    try:
        aid = places.attend(user["id"], body.place_key, body.place_name, body.place_type, body.dest, body.lat, body.lng, _day(body.day))
    except places.PlaceError as exc:
        _fail(exc)
    activity.record("attend.added", place=body.place_key, day=(body.day or date.today()).isoformat())
    return {"id": aid}


@router.delete("/api/people/attend/{attendance_id}")
def unattend(attendance_id: int, user: dict = Depends(current_user)):
    """Cancel a registration."""
    if not places.leave(user["id"], attendance_id):
        raise HTTPException(status_code=404, detail="Not found.")
    return {"ok": True}


@router.get("/api/people/attendees")
def attendees(place_key: str, day: date | None = None, user: dict = Depends(current_user)):
    """Who is going to a place on a day (discoverable people only, never anyone who blocked or was blocked)."""
    return places.attendees(user["id"], place_key, _day(day))


# ---------------------------------------------------------------- finding people

class LookingIn(BaseModel):
    text: str = Field(min_length=4, max_length=600)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    radius_m: int = Field(default=3000, ge=500, le=25000)


@router.post("/api/people/looking")
async def looking(body: LookingIn, request: Request, user: dict = Depends(current_user)):
    """Describe an activity and the company you want. The AI reads it into tags, and we return matching people nearby."""
    security.limit(f"people-looking:{user['id']}", 30, 3600)
    try:
        parsed = await asyncio.wait_for(asyncio.to_thread(intents.parse, body.text), timeout=45)
        iid = intents.create(user["id"], body.text, body.lat, body.lng, body.radius_m, parsed)
    except intents.IntentError as exc:
        _fail(exc)
    activity.record("intent.created", tags=",".join(parsed["tags"]))
    row = intents.get_mine(user["id"], iid)
    return {"request": intents._shape(row), "notes": parsed["notes"], **intents.find(user["id"], row)}


@router.get("/api/people/looking/{intent_id}/matches")
def matches(intent_id: int, user: dict = Depends(current_user)):
    """Refresh the matches for one of my open requests."""
    row = intents.get_mine(user["id"], intent_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found.")
    return {"request": intents._shape(row), **intents.find(user["id"], row)}


@router.delete("/api/people/looking/{intent_id}")
def stop_looking(intent_id: int, user: dict = Depends(current_user)):
    """Close one of my requests so I stop showing up in other people's matches."""
    if not intents.close(user["id"], intent_id):
        raise HTTPException(status_code=404, detail="Not found.")
    return {"ok": True}


# ---------------------------------------------------------------- connections and chat

class ConnectIn(BaseModel):
    to_user: int
    message: str = Field(default="", max_length=200)


@router.post("/api/people/connect")
def connect_request(body: ConnectIn, user: dict = Depends(current_user)):
    """Ask to connect. Chat opens only if the other person accepts."""
    try:
        result = connect.request(user["id"], body.to_user, body.message)
    except connect.ConnectError as exc:
        _fail(exc)
    activity.record("connection.accepted" if result["status"] == "accepted" else "connection.requested")
    return result


@router.get("/api/people/connections")
def connections(user: dict = Depends(current_user)):
    """Requests I received, requests I sent, and my open chats."""
    return connect.overview(user["id"])


class RespondIn(BaseModel):
    accept: bool


@router.post("/api/people/connections/{connection_id}/respond")
def respond(connection_id: int, body: RespondIn, user: dict = Depends(current_user)):
    """Accept or decline a request I received."""
    if not connect.respond(user["id"], connection_id, body.accept):
        raise HTTPException(status_code=404, detail="Not found.")
    if body.accept:
        activity.record("connection.accepted")
    return {"ok": True}


@router.get("/api/people/chats/{connection_id}/messages")
def chat_messages(connection_id: int, after: int = 0, user: dict = Depends(current_user)):
    """Messages in a chat, newer than `after`. The app polls this every few seconds while a chat is open."""
    try:
        return {"messages": connect.messages(user["id"], connection_id, after)}
    except connect.ConnectError as exc:
        _fail(exc)


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=500)


@router.post("/api/people/chats/{connection_id}/messages")
def chat_send(connection_id: int, body: MessageIn, user: dict = Depends(current_user)):
    """Send a message in an accepted chat."""
    try:
        return connect.send(user["id"], connection_id, body.body)
    except connect.ConnectError as exc:
        _fail(exc)


# ---------------------------------------------------------------- safety

class BlockIn(BaseModel):
    user_id: int


@router.post("/api/people/block")
def block(body: BlockIn, user: dict = Depends(current_user)):
    """Block someone: you disappear from each other everywhere and any chat closes."""
    try:
        users.block(user["id"], body.user_id)
    except users.UserError as exc:
        _fail(exc)
    return {"ok": True}


@router.post("/api/people/unblock")
def unblock(body: BlockIn, user: dict = Depends(current_user)):
    """Undo a block."""
    users.unblock(user["id"], body.user_id)
    return {"ok": True}


class ReportIn(BaseModel):
    user_id: int
    reason: str = Field(max_length=40)
    detail: str = Field(default="", max_length=500)
    message_id: int | None = None


@router.post("/api/people/report")
def report(body: ReportIn, request: Request, user: dict = Depends(current_user)):
    """Report a person (optionally a message) to the moderators."""
    security.limit(f"people-report:{user['id']}", 20, 86400)
    try:
        rid = connect.report(user["id"], body.user_id, body.reason, body.detail, body.message_id)
    except connect.ConnectError as exc:
        _fail(exc)
    activity.record("report.filed", reason=body.reason)
    return {"id": rid, "note": "Thank you. A moderator will review this. You can also block the person."}


# ---------------------------------------------------------------- moderation (admin token)

@router.get("/api/admin/people/photos", dependencies=[Depends(admin_required)])
def admin_photos():
    """Profile photos waiting for a human decision."""
    return {"photos": users.pending_photos()}


@router.post("/api/admin/people/photos/{user_id}/approve", dependencies=[Depends(admin_required)])
def admin_photo_approve(user_id: int):
    """Approve a pending profile photo."""
    if not users.review_photo(user_id, True):
        raise HTTPException(status_code=404, detail="No pending photo.")
    activity.record("photo.approved")
    return {"ok": True}


@router.post("/api/admin/people/photos/{user_id}/reject", dependencies=[Depends(admin_required)])
def admin_photo_reject(user_id: int):
    """Reject a pending profile photo and delete the file."""
    if not users.review_photo(user_id, False):
        raise HTTPException(status_code=404, detail="No pending photo.")
    activity.record("photo.rejected")
    return {"ok": True}


@router.get("/api/admin/people/reports", dependencies=[Depends(admin_required)])
def admin_reports():
    """Open reports against people, with how many are open against each person."""
    return {"reports": connect.open_reports()}


class ResolveIn(BaseModel):
    ban: bool


@router.post("/api/admin/people/reports/{report_id}/resolve", dependencies=[Depends(admin_required)])
def admin_resolve(report_id: int, body: ResolveIn):
    """Close a report, optionally banning the person (their sessions end at once)."""
    if not connect.resolve_report(report_id, body.ban):
        raise HTTPException(status_code=404, detail="No such open report.")
    activity.record("user.banned" if body.ban else "report.dismissed")
    return {"ok": True}
