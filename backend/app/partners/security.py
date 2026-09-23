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

# The most commonly leaked passwords (from public breach-corpus frequency lists), checked at registration and
# when changing a password. A short, offline, no-network denylist -- not a policy substitute for length.
COMMON_PASSWORDS = frozenset({
    "123456789", "1234567890", "password", "password1", "password123", "qwertyuiop", "1q2w3e4r5t",
    "1qaz2wsx3edc", "letmein123", "welcome123", "iloveyou1", "trustno1a", "dragon1234", "monkey1234",
    "football1", "baseball1", "superman1", "princess1", "sunshine1", "master1234", "shadow1234",
    "michael123", "jennifer1", "computer1", "qwerty123", "abc123456", "1234567890a", "changeme1",
    "administrator", "letmeinnow", "passw0rd1", "p@ssw0rd1", "temppassword", "temporary1",
    "newpassword", "testpassword", "testpassword1", "wayfinder123", "wayfinder1234",
})


def is_weak_password(password: str) -> str | None:
    """None if the password is acceptable, else a message explaining why not."""
    if len(password) < MIN_PASSWORD:
        return f"Use a password of at least {MIN_PASSWORD} characters."
    if password.lower() in COMMON_PASSWORDS:
        return "That password is too common. Please choose a less guessable one."
    return None


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
