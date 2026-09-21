"""OpenAI features: plain-English trip requests and grounded explanations.

Uses the plain HTTPS API (no SDK). The key comes from OPENAI_API_KEY (backend/.env, never committed).
The model NEVER supplies prices or facts: it only reads structured data we already have. Its output is
validated (destination codes must exist, dates must parse) and any explanation containing a number that
is not in the source facts is rejected.
"""
import json
import logging
import re
from datetime import date, timedelta

from app.config import openai_base_url, openai_key, openai_model
from app.live import catalog
from app.live.osm import PLACE_TYPES
from app.live.http import client

logger = logging.getLogger(__name__)

INTERESTS = ["beachfront", "nightlife", "food-scene", "old-town", "spa", "quiet", "pet-friendly"]


def enabled() -> bool:
    return openai_key() is not None


def _chat(system: str, user: str, max_tokens: int = 600, image: str | None = None) -> dict:
    """One JSON-mode chat call. `image` is an optional data URL sent to a vision-capable model."""
    content = user if not image else [{"type": "text", "text": user}, {"type": "image_url", "image_url": {"url": image, "detail": "low"}}]
    with client(60) as c:
        r = c.post(
            f"{openai_base_url()}/chat/completions",
            headers={"Authorization": f"Bearer {openai_key()}"},
            json={
                "model": openai_model(),
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
                "response_format": {"type": "json_object"},
                "max_completion_tokens": max_tokens,
            },
        )
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])


# ---------- plain-English request -> form fields ----------

def normalize_request(raw: dict, today: date) -> dict:
    """Validate whatever the model returned; keep only fields we can trust."""
    out: dict = {}
    for key in ("origin", "destination"):
        dest = catalog.resolve(str(raw.get(key) or ""))
        if dest:
            out[key] = dest["code"]

    def to_date(v):
        try:
            return date.fromisoformat(str(v))
        except (TypeError, ValueError):
            return None

    start, end = to_date(raw.get("start_date")), to_date(raw.get("end_date"))
    nights = raw.get("nights")
    if start and not end and isinstance(nights, (int, float)) and 1 <= nights <= 60:
        end = start + timedelta(days=int(nights))
    if start and end and end > start and start >= today - timedelta(days=1):
        out["start_date"], out["end_date"] = start.isoformat(), end.isoformat()

    budget = raw.get("budget")
    if isinstance(budget, (int, float)) and budget > 0:
        out["budget"] = float(budget)
    travelers = raw.get("travelers")
    if isinstance(travelers, int) and 1 <= travelers <= 12:
        out["travelers"] = travelers
    interests = [i for i in _as_list(raw.get("interests")) if i in INTERESTS]
    if interests:
        out["interests"] = interests
    out["assumptions"] = [str(a)[:160] for a in _as_list(raw.get("assumptions"))][:5]
    return out


def _as_list(value) -> list:
    """Models sometimes return a single string where a list was asked for; never split it into characters."""
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def parse_trip_request(text: str, today: date | None = None) -> dict:
    today = today or date.today()
    places = ", ".join(f"{d['code']}={d['city']}" for d in catalog.DESTINATIONS)
    system = (
        "You turn a traveler's free-text trip request into JSON. Reply with a JSON object with these keys: "
        "origin, destination (each MUST be one of these codes: " + places + " ; use null if unclear or not listed), "
        "start_date, end_date (ISO YYYY-MM-DD), nights (integer, only if dates are not given), budget (number, "
        "total for the trip; assume GBP), travelers (integer), interests (a subset of: " + ", ".join(INTERESTS) + "), "
        "assumptions (short strings describing anything you had to guess). "
        f"Today is {today.isoformat()}; resolve relative dates such as 'next month' to future dates. "
        "Never invent details the traveler did not imply; use null instead."
    )
    return normalize_request(_chat(system, text[:1200], 500), today)


# ---------- traveler profile (text, and optionally a photo) ----------

VIBES = ["relaxed", "adventurous", "cultural", "romantic", "social", "family", "luxurious", "budget-savvy"]
PACES = ["relaxed", "balanced", "packed"]
BUDGET_STYLES = ["budget", "mid-range", "premium"]
MAX_IMAGE_CHARS = 2_000_000  # roughly a 1.5 MB image once base64-encoded


def normalize_profile(raw: dict | None) -> dict:
    """Validate the model's profile: known interest and place-type keys only, bounded text."""
    raw = raw or {}
    keywords = [str(k).strip().lower()[:30] for k in _as_list(raw.get("keywords")) if str(k).strip()][:8]
    return {
        "summary": str(raw.get("summary") or "")[:300],
        "keywords": keywords,
        "interests": [i for i in _as_list(raw.get("interests")) if i in INTERESTS],
        "place_types": [p for p in _as_list(raw.get("place_types")) if p in PLACE_TYPES],
        "vibe": raw.get("vibe") if raw.get("vibe") in VIBES else None,
        "pace": raw.get("pace") if raw.get("pace") in PACES else None,
        "budget_style": raw.get("budget_style") if raw.get("budget_style") in BUDGET_STYLES else None,
    }


def valid_image(data_url: str | None) -> bool:
    return bool(data_url) and len(data_url) <= MAX_IMAGE_CHARS and re.match(r"^data:image/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$", data_url) is not None


def build_trip(text: str, image: str | None = None, today: date | None = None) -> dict:
    """Free text (and optionally one photo) -> trip fields plus a traveler profile with the place types
    they would enjoy. The photo is only a hint about taste; the model is told not to identify anyone."""
    today = today or date.today()
    places = ", ".join(f"{d['code']}={d['city']}" for d in catalog.DESTINATIONS)
    types = ", ".join(f"{k} ({v[0]})" for k, v in PLACE_TYPES.items())
    system = (
        "You build a trip and a traveler profile from what the person wrote" + (" and the photo they shared" if image else "") + ". "
        "Reply with one JSON object with two keys. 'trip': origin, destination (each MUST be one of these codes: " + places + "; null if unclear), "
        "start_date, end_date (ISO), nights (integer, only if no dates), budget (number, GBP total), travelers (integer), "
        "assumptions (list of short strings for anything you guessed). "
        "'profile': summary (max 2 sentences, addressed to 'you'), keywords (up to 8 short words for what they like), "
        "interests (subset of: " + ", ".join(INTERESTS) + "), place_types (subset of: " + types + " - choose the kinds of places they would want to visit), "
        "vibe (one of: " + ", ".join(VIBES) + "), pace (one of: " + ", ".join(PACES) + "), budget_style (one of: " + ", ".join(BUDGET_STYLES) + "). "
        f"Today is {today.isoformat()}; resolve relative dates to the future. Never invent details; use null or an empty list instead. "
        + ("The photo is only a hint about the atmosphere and activities they like (scenery, food, nightlife, culture). Never identify or describe any person in it. " if image else "")
    )
    raw = _chat(system, text[:1500] or "(no text, use the photo)", 700, image if valid_image(image) else None)
    result = normalize_request(raw.get("trip") or {}, today)
    result["profile"] = normalize_profile(raw.get("profile"))
    return result


# ---------- grounded explanation ----------

def _canon(n: str) -> str:
    """'05' and '5' are the same number; so are '900.0' and '900'."""
    n = n.replace(",", "")
    if "." in n:
        n = n.rstrip("0").rstrip(".")
    return n.lstrip("0") or "0"


def _numbers(text: str) -> set[str]:
    return {_canon(n) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def is_grounded(text: str, facts: dict) -> bool:
    """True only if every number the model wrote also appears in the facts we gave it."""
    return _numbers(text) <= _numbers(json.dumps(facts, ensure_ascii=False))


def summarize(facts: dict) -> str | None:
    system = (
        "You write a short trip summary (3 sentences max) for a traveler from the JSON facts provided. "
        "Use ONLY these facts. Do not add prices, opening hours, ratings, names or claims that are not in the facts. "
        "Copy numbers exactly as given; never calculate new ones (no totals, averages or conversions). "
        "If a price source is 'estimate', say it is an estimate. Reply as JSON: {\"summary\": \"...\"}."
    )
    facts_json = json.dumps(facts, ensure_ascii=False)
    allowed = sorted(_numbers(facts_json), key=lambda n: (len(n), n))
    note = ""
    for _attempt in range(2):
        text = _chat(system + note, facts_json, 300).get("summary")
        if not (isinstance(text, str) and text.strip()):
            continue
        invented = _numbers(text) - _numbers(facts_json)
        if not invented:
            return text.strip()
        logger.warning("AI summary rejected, numbers not in the facts: %s", sorted(invented))
        note = (
            f" Your previous answer used numbers that are not in the facts ({', '.join(sorted(invented))}). "
            f"Only these numbers may appear: {', '.join(allowed)}. Do not calculate new numbers, and write "
            "anything you are unsure about in words instead of digits."
        )
    return None  # discard anything that could contain an invented number
