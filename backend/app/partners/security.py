"""Passwords, session tokens, API keys and a small rate limiter. Standard library only.

- Passwords: scrypt with a random salt (never stored in the clear).
- Session tokens and API keys: random, shown once, stored only as SHA-256 hashes.
- Comparisons use hmac.compare_digest to avoid timing leaks.
"""
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque

from fastapi import HTTPException

SESSION_SECONDS = 7 * 24 * 3600
MIN_PASSWORD = 10


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def new_api_key() -> str:
    return "wfk_" + secrets.token_urlsafe(24)


def same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


_hits: dict[str, deque] = defaultdict(deque)


def limit(key: str, max_hits: int, window_s: int) -> None:
    """Raise 429 when `key` has been used more than `max_hits` times in the last `window_s` seconds."""
    now = time.time()
    q = _hits[key]
    while q and now - q[0] > window_s:
        q.popleft()
    if len(q) >= max_hits:
        raise HTTPException(status_code=429, detail="Too many attempts. Please wait a few minutes and try again.")
    q.append(now)


def reset_limits() -> None:
    _hits.clear()
