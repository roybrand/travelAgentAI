"""Small HTTP + disk-cache helpers shared by the live data modules."""
import json
import re
import time
from pathlib import Path
from typing import Any, Callable

import httpx

from app.config import CACHE_DIR

USER_AGENT = "WayfinderPrototype/0.2 (trip planner demo; contact roybran@gmail.com)"
DAY = 86400


def client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT})


def get_json(url: str, params: dict | None = None, timeout: float = 30.0, headers: dict | None = None, attempts: int = 3) -> Any:
    """GET + parse JSON, retrying transient failures (connection errors, 429, 5xx) with a short backoff.
    Free public APIs blip now and then; one hiccup should not fail a whole trip search."""
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            with client(timeout) as c:
                r = c.get(url, params=params, headers=headers)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
                r.raise_for_status()
                return r.json()
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            last = exc
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 429:
                raise  # a real client error (e.g. 404) will not get better by retrying
            time.sleep(1.5 * (attempt + 1))
    raise last


def _path(key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", key)
    return CACHE_DIR / f"{safe}.json"


def peek(key: str, ttl_seconds: float) -> Any | None:
    """Fresh cached data if there is any, else None. Never fetches."""
    path = _path(key)
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return stored["data"] if time.time() - stored["ts"] < ttl_seconds else None


def cached(key: str, ttl_seconds: float, fetch: Callable[[], Any]) -> Any:
    """Return fresh cached data, else call fetch() and store it. If fetch fails, fall back to stale
    cached data rather than failing; raise only when there is nothing at all to serve."""
    path = _path(key)
    stored = None
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            stored = None
    if stored and time.time() - stored["ts"] < ttl_seconds:
        return stored["data"]
    try:
        data = fetch()
    except Exception:
        if stored:
            return stored["data"]
        raise
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"ts": time.time(), "data": data}), encoding="utf-8")
    except OSError:
        pass  # a read-only disk should not break a request
    return data
