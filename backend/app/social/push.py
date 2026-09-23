"""Real Web Push notifications (RFC 8291 message encryption, RFC 8292 VAPID authentication) for new messages
and connection requests -- the one place this app reaches a device even while it is fully closed, not just
open in a background tab. A subscription belongs to a Wayfinder People account, the one durable identity in
this app.

No SDK: built directly on `cryptography`'s primitives, the way the rest of this codebase avoids wrapper
libraries for its other optional integrations (see app/partners/stripe_gateway.py for the same approach).
Enabled only when VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY and VAPID_SUBJECT are all set; generate a free pair
with `python scripts/generate_vapid_keys.py`.

NOTE: this follows the RFCs closely and was exercised end to end against a real Chrome subscription during
development (see docs/09-people-and-safety.md), but has not been run against Apple's push service.
"""
import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric import utils as ec_utils
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand

from app.config import vapid_keys
from app.live.http import client
from app.partners import db

TTL_SECONDS = 60 * 60 * 12   # how long a push service may hold an undelivered message
JWT_LIFETIME = 60 * 60 * 12  # RFC 8292 recommends well under 24 hours
RECORD_SIZE = 4096           # a fixed, generous "rs" (RFC 8188); our single record is always far smaller


def enabled() -> bool:
    return vapid_keys() is not None


def public_key() -> str | None:
    keys = vapid_keys()
    return keys[0] if keys else None


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64u(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _private_key() -> ec.EllipticCurvePrivateKey:
    _, priv_b64, _ = vapid_keys()
    return ec.derive_private_key(int.from_bytes(_unb64u(priv_b64), "big"), ec.SECP256R1())


def _vapid_jwt(endpoint: str) -> str:
    """A short-lived, self-signed proof of who sent this (RFC 8292), so a push service can identify the sender."""
    parts = urlsplit(endpoint)
    aud = f"{parts.scheme}://{parts.netloc}"
    _, _, subject = vapid_keys()
    header = _b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    claims = _b64u(json.dumps({"aud": aud, "exp": int(time.time()) + JWT_LIFETIME, "sub": subject}, separators=(",", ":")).encode())
    signing_input = f"{header}.{claims}".encode()
    der_sig = _private_key().sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = ec_utils.decode_dss_signature(der_sig)
    raw_sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")  # JWS wants raw R||S, not the DER signature
    return f"{header}.{claims}.{_b64u(raw_sig)}"


def _hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    return hmac.new(salt, ikm, hashlib.sha256).digest()


def _hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    return HKDFExpand(algorithm=hashes.SHA256(), length=length, info=info).derive(prk)


def _encrypt(plaintext: bytes, ua_public_b64: str, auth_secret_b64: str) -> bytes:
    """RFC 8291 message encryption, as the single "aes128gcm" (RFC 8188) record a push payload always is."""
    ua_public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), _unb64u(ua_public_b64))
    auth_secret = _unb64u(auth_secret_b64)

    as_private = ec.generate_private_key(ec.SECP256R1())  # a fresh keypair per message
    as_public_raw = as_private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    ua_public_raw = ua_public.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)

    shared_secret = as_private.exchange(ec.ECDH(), ua_public)
    key_info = b"WebPush: info\x00" + ua_public_raw + as_public_raw
    prk_key = _hkdf_extract(auth_secret, shared_secret)
    ikm = _hkdf_expand(prk_key, key_info, 32)

    salt = os.urandom(16)
    prk = _hkdf_extract(salt, ikm)
    cek = _hkdf_expand(prk, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf_expand(prk, b"Content-Encoding: nonce\x00", 12)

    record = plaintext + b"\x02"  # the padding delimiter octet for the one (and so "last") record; no extra padding
    ciphertext = AESGCM(cek).encrypt(nonce, record, None)

    header = salt + RECORD_SIZE.to_bytes(4, "big") + bytes([len(as_public_raw)]) + as_public_raw
    return header + ciphertext


def send(endpoint: str, p256dh: str, auth: str, title: str, body: str, url: str, ttl: int = TTL_SECONDS) -> int:
    """POST one encrypted message to a subscription's endpoint. Returns the push service's status code;
    404 or 410 means the subscription no longer exists and should be forgotten."""
    payload = json.dumps({"title": title[:120], "body": body[:200], "url": url}).encode()
    encrypted = _encrypt(payload, p256dh, auth)
    headers = {
        "Content-Type": "application/octet-stream", "Content-Encoding": "aes128gcm",
        "TTL": str(ttl), "Authorization": f"vapid t={_vapid_jwt(endpoint)}, k={public_key()}",
    }
    with client(10) as c:
        r = c.post(endpoint, content=encrypted, headers=headers)
        return r.status_code


# ---------------------------------------------------------------- subscriptions (People account)

def subscribe(user_id: int, endpoint: str, p256dh: str, auth: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with db.tx() as c:
        c.execute(
            "INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, created_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(endpoint) DO UPDATE SET user_id = excluded.user_id, p256dh = excluded.p256dh, auth = excluded.auth",
            (user_id, endpoint, p256dh, auth, now))


def unsubscribe(user_id: int, endpoint: str) -> None:
    with db.tx() as c:
        c.execute("DELETE FROM push_subscriptions WHERE user_id = ? AND endpoint = ?", (user_id, endpoint))


def notify_user(user_id: int, title: str, body: str, url: str = "/people") -> None:
    """Push every device this person has subscribed on. Best-effort: a failed or stale send is dropped, and
    never raises, so it can never break the chat or connection request that triggered it."""
    if not enabled():
        return
    with db.tx() as c:
        rows = c.execute("SELECT id, endpoint, p256dh, auth FROM push_subscriptions WHERE user_id = ?", (user_id,)).fetchall()
    for row in rows:
        try:
            status = send(row["endpoint"], row["p256dh"], row["auth"], title, body, url)
        except Exception:
            continue
        if status in (404, 410):
            with db.tx() as c:
                c.execute("DELETE FROM push_subscriptions WHERE id = ?", (row["id"],))
