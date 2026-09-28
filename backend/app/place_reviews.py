"""Wayfinder-owned place profiles, reviews and traveler photos.

External providers can name a place and provide coordinates, but our app owns the community layer:
stable place records, first-party reviews, submitted photos, and moderation state.
"""
import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from app import config
from app.partners import db
from app.partners.routes import admin_required
from app.social.moderation import check_image, check_text, decode_photo
from app.social.routes import current_user

router = APIRouter()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def photo_dir() -> Path:
    d = config.db_path().parent / "place_photos"
    d.mkdir(parents=True, exist_ok=True)
    return d


def clean_key(value: str) -> str:
    return re.sub(r"[^a-z0-9:.|_-]+", "-", value.lower()).strip("-")[:180]


def place_key(p: dict) -> str:
    for k in ("key", "id", "osm_url", "wikidata", "wikipedia", "website", "url"):
        v = str(p.get(k) or "").strip()
        if v:
            return clean_key(v)
    name = str(p.get("name") or "place").strip().lower()
    lat = p.get("lat")
    lng = p.get("lng")
    if lat is not None and lng is not None:
        return clean_key(f"{name}|{float(lat):.5f}|{float(lng):.5f}")
    return clean_key(name)


class PlaceIn(BaseModel):
    key: str | None = Field(default=None, max_length=240)
    id: str | None = Field(default=None, max_length=240)
    name: str = Field(min_length=1, max_length=180)
    type: str | None = Field(default=None, max_length=60)
    typeLabel: str | None = Field(default=None, max_length=80)
    city: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    area: str | None = Field(default=None, max_length=180)
    route_stop: str | None = Field(default=None, max_length=180)
    osm_url: str | None = Field(default=None, max_length=500)
    wikidata: str | None = Field(default=None, max_length=80)
    wikipedia: str | None = Field(default=None, max_length=500)
    website: str | None = Field(default=None, max_length=500)
    url: str | None = Field(default=None, max_length=500)
    source: str | None = Field(default=None, max_length=60)
    why: str | None = Field(default=None, max_length=800)
    photo_url: str | None = Field(default=None, max_length=800)
    photo_credit: dict | str | None = None


class PlaceBody(BaseModel):
    place: PlaceIn


class ReviewIn(PlaceBody):
    rating: int = Field(ge=1, le=5)
    body: str = Field(min_length=12, max_length=1200)
    visit_date: date | None = None


class PhotoIn(PlaceBody):
    image: str | None = Field(default=None, max_length=600_000)
    photo_url: str | None = Field(default=None, max_length=800)
    caption: str = Field(default="", max_length=240)
    credit: str = Field(default="", max_length=160)

    @model_validator(mode="after")
    def has_photo(self):
        if not self.image and not self.photo_url:
            raise ValueError("Add a photo or a photo URL.")
        return self


class ModerationIn(BaseModel):
    reason: str = Field(default="", max_length=300)


def _credit(value) -> str:
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)[:1000]
    return str(value or "")[:1000]


def _description(p: PlaceIn) -> str:
    bits = [p.why, p.typeLabel, p.area, p.route_stop, p.city]
    text = " · ".join(str(x).strip() for x in bits if str(x or "").strip())
    return text[:800]


def upsert_place(raw: PlaceIn) -> dict:
    p = raw.model_dump()
    key = place_key(p)
    ts = now()
    with db.tx() as c:
        row = c.execute("SELECT * FROM places WHERE place_key = ?", (key,)).fetchone()
        values = (
            raw.name.strip(),
            raw.type,
            raw.typeLabel,
            raw.city or raw.area,
            raw.country,
            raw.lat,
            raw.lng,
            raw.osm_url,
            raw.wikidata,
            raw.wikipedia or raw.url,
            raw.website,
            raw.source,
            _description(raw),
            raw.photo_url,
            _credit(raw.photo_credit),
            ts,
            key,
        )
        if row:
            c.execute(
                "UPDATE places SET name = ?, type = COALESCE(?, type), type_label = COALESCE(?, type_label), "
                "city = COALESCE(?, city), country = COALESCE(?, country), lat = COALESCE(?, lat), lng = COALESCE(?, lng), "
                "osm_url = COALESCE(?, osm_url), wikidata = COALESCE(?, wikidata), wikipedia = COALESCE(?, wikipedia), "
                "website = COALESCE(?, website), source = COALESCE(?, source), description = COALESCE(NULLIF(?, ''), description), "
                "photo_url = COALESCE(?, photo_url), photo_credit = COALESCE(?, photo_credit), updated_at = ? WHERE place_key = ?",
                values,
            )
        else:
            c.execute(
                "INSERT INTO places (place_key, name, type, type_label, city, country, lat, lng, osm_url, wikidata, wikipedia, "
                "website, source, description, photo_url, photo_credit, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (key, raw.name.strip(), raw.type, raw.typeLabel, raw.city or raw.area, raw.country, raw.lat, raw.lng,
                 raw.osm_url, raw.wikidata, raw.wikipedia or raw.url, raw.website, raw.source, _description(raw),
                 raw.photo_url, _credit(raw.photo_credit), ts, ts),
            )
        return dict(c.execute("SELECT * FROM places WHERE place_key = ?", (key,)).fetchone())


def _review_summary(c, place_id: int) -> dict:
    rows = c.execute("SELECT rating FROM place_reviews WHERE place_id = ? AND status = 'approved'", (place_id,)).fetchall()
    if not rows:
        return {"count": 0, "average": None}
    avg = round(sum(r["rating"] for r in rows) / len(rows), 1)
    return {"count": len(rows), "average": avg}


def _shape_place(row, c) -> dict:
    reviews = [
        {"id": r["id"], "rating": r["rating"], "body": r["body"], "visit_date": r["visit_date"], "helpful_count": r["helpful_count"],
         "created_at": r["created_at"], "user": r["display_name"] or "Traveler"}
        for r in c.execute(
            "SELECT pr.*, u.display_name FROM place_reviews pr LEFT JOIN users u ON u.id = pr.user_id "
            "WHERE pr.place_id = ? AND pr.status = 'approved' ORDER BY pr.created_at DESC LIMIT 20",
            (row["id"],),
        )
    ]
    photos = []
    if row["photo_url"]:
        photos.append({"url": row["photo_url"], "credit": row["photo_credit"], "caption": "Source photo", "source": "external"})
    photos.extend(
        {"id": p["id"], "url": p["photo_url"] or f"/api/place-photos/{p['file_name']}", "credit": p["credit"],
         "caption": p["caption"], "source": "traveler"}
        for p in c.execute("SELECT * FROM place_photos WHERE place_id = ? AND status = 'approved' ORDER BY created_at DESC LIMIT 12", (row["id"],))
    )
    return {
        "place": dict(row),
        "summary": _review_summary(c, row["id"]),
        "reviews": reviews,
        "photos": photos,
    }


def _status_from_moderation(flagged: bool | None) -> str:
    return "rejected" if flagged is True else "approved" if flagged is False else "pending"


@router.post("/api/places/detail")
def place_detail(body: PlaceBody):
    place = upsert_place(body.place)
    with db.tx() as c:
        return _shape_place(c.execute("SELECT * FROM places WHERE id = ?", (place["id"],)).fetchone(), c)


@router.post("/api/places/reviews")
def create_review(body: ReviewIn, user: dict = Depends(current_user)):
    place = upsert_place(body.place)
    flagged = check_text(body.body)
    status = _status_from_moderation(flagged)
    ts = now()
    with db.tx() as c:
        c.execute(
            "INSERT INTO place_reviews (place_id, user_id, rating, body, visit_date, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (place["id"], user["id"], body.rating, body.body.strip(), body.visit_date.isoformat() if body.visit_date else None, status, ts, ts),
        )
        row = c.execute("SELECT * FROM places WHERE id = ?", (place["id"],)).fetchone()
        shaped = _shape_place(row, c)
    return {**shaped, "submitted_status": status}


@router.post("/api/places/photos")
def create_photo(body: PhotoIn, user: dict = Depends(current_user)):
    place = upsert_place(body.place)
    flagged = check_image(body.image) if body.image else check_text(body.caption or body.photo_url or "")
    status = _status_from_moderation(flagged)
    file_name = None
    if body.image:
        try:
            raw, ext = decode_photo(body.image)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        digest = hashlib.sha256(raw).hexdigest()[:24]
        file_name = f"{place['id']}-{digest}.{ext}"
        (photo_dir() / file_name).write_bytes(raw)
    with db.tx() as c:
        c.execute(
            "INSERT INTO place_photos (place_id, user_id, file_name, photo_url, credit, caption, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (place["id"], user["id"], file_name, body.photo_url, body.credit.strip(), body.caption.strip(), status, now()),
        )
        row = c.execute("SELECT * FROM places WHERE id = ?", (place["id"],)).fetchone()
        shaped = _shape_place(row, c)
    return {**shaped, "submitted_status": status}


@router.get("/api/place-photos/{file_name}")
def get_place_photo(file_name: str):
    safe = Path(file_name).name
    with db.tx() as c:
        row = c.execute("SELECT * FROM place_photos WHERE file_name = ? AND status = 'approved'", (safe,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found.")
    path = photo_dir() / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail="Photo not found.")
    return FileResponse(path)


@router.get("/api/admin/place-reviews", dependencies=[Depends(admin_required)])
def admin_pending_places():
    with db.tx() as c:
        reviews = [dict(r) for r in c.execute(
            "SELECT pr.*, p.name AS place_name, u.display_name FROM place_reviews pr "
            "JOIN places p ON p.id = pr.place_id LEFT JOIN users u ON u.id = pr.user_id "
            "WHERE pr.status = 'pending' ORDER BY pr.created_at DESC LIMIT 100"
        )]
        photos = [dict(p) for p in c.execute(
            "SELECT pp.*, pl.name AS place_name, u.display_name FROM place_photos pp "
            "JOIN places pl ON pl.id = pp.place_id LEFT JOIN users u ON u.id = pp.user_id "
            "WHERE pp.status = 'pending' ORDER BY pp.created_at DESC LIMIT 100"
        )]
    return {"reviews": reviews, "photos": photos}


@router.post("/api/admin/place-reviews/{review_id}/approve", dependencies=[Depends(admin_required)])
def approve_review(review_id: int):
    with db.tx() as c:
        if not c.execute("UPDATE place_reviews SET status = 'approved', updated_at = ? WHERE id = ?", (now(), review_id)).rowcount:
            raise HTTPException(status_code=404, detail="Review not found.")
    return {"ok": True}


@router.post("/api/admin/place-reviews/{review_id}/reject", dependencies=[Depends(admin_required)])
def reject_review(review_id: int, body: ModerationIn):
    with db.tx() as c:
        if not c.execute("UPDATE place_reviews SET status = 'rejected', updated_at = ? WHERE id = ?", (now(), review_id)).rowcount:
            raise HTTPException(status_code=404, detail="Review not found.")
    return {"ok": True, "reason": body.reason}


@router.post("/api/admin/place-photos/{photo_id}/approve", dependencies=[Depends(admin_required)])
def approve_photo(photo_id: int):
    with db.tx() as c:
        if not c.execute("UPDATE place_photos SET status = 'approved' WHERE id = ?", (photo_id,)).rowcount:
            raise HTTPException(status_code=404, detail="Photo not found.")
    return {"ok": True}


@router.post("/api/admin/place-photos/{photo_id}/reject", dependencies=[Depends(admin_required)])
def reject_photo(photo_id: int, body: ModerationIn):
    with db.tx() as c:
        if not c.execute("UPDATE place_photos SET status = 'rejected' WHERE id = ?", (photo_id,)).rowcount:
            raise HTTPException(status_code=404, detail="Photo not found.")
    return {"ok": True, "reason": body.reason}
