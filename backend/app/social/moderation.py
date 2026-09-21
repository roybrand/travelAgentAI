"""Content checks for profile photos and chat messages.

OpenAI's moderation endpoint is free and covers text and images. When a key is set, flagged content is refused.
With no key, photos wait for a human (the moderator queue at /admin) and text is checked only for length.
"""
import base64
import re

from app.config import openai_base_url, openai_key
from app.live.http import client

MAX_PHOTO_BYTES = 400_000
_DATA_URL = re.compile(r"^data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=]+)$")
_MAGIC = {"jpeg": (b"\xff\xd8\xff",), "png": (b"\x89PNG\r\n\x1a\n",), "webp": (b"RIFF",)}


def enabled() -> bool:
    return openai_key() is not None


def decode_photo(data_url: str) -> tuple[bytes, str]:
    """Validate a data URL: a real JPEG, PNG or WebP no bigger than 400 KB. Returns (bytes, extension)."""
    m = _DATA_URL.match(data_url or "")
    if not m:
        raise ValueError("Use a JPEG, PNG or WebP photo.")
    kind = m.group(1)
    raw = base64.b64decode(m.group(2), validate=True)
    if len(raw) > MAX_PHOTO_BYTES:
        raise ValueError("That photo is too big. Choose a smaller one (under 400 KB).")
    if not raw.startswith(_MAGIC[kind]) or (kind == "webp" and raw[8:12] != b"WEBP"):
        raise ValueError("That file is not a valid image.")
    return raw, "jpg" if kind == "jpeg" else kind


def _moderate(payload) -> bool | None:
    """True if flagged, False if fine, None if we could not check."""
    if not enabled():
        return None
    try:
        with client(30) as c:
            r = c.post(f"{openai_base_url()}/moderations", headers={"Authorization": f"Bearer {openai_key()}"},
                       json={"model": "omni-moderation-latest", "input": payload})
            r.raise_for_status()
            return bool(r.json()["results"][0]["flagged"])
    except Exception:
        return None


def check_text(text: str) -> bool | None:
    return _moderate(text)


def check_image(data_url: str) -> bool | None:
    return _moderate([{"type": "image_url", "image_url": {"url": data_url}}])
