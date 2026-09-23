"""Optional real payments via Stripe Checkout (free test-mode account at https://stripe.com), used for
Featured deal placements -- the only thing money buys on Wayfinder; it never touches ranking (see
app/partners/featured.py). Enabled only when STRIPE_SECRET_KEY is set; STRIPE_WEBHOOK_SECRET is required
too, to trust the webhook that confirms a payment actually went through. Uses the plain HTTPS API (no SDK),
like the other paid integrations in this codebase.

NOTE: this follows Stripe's documented request shape and webhook signature scheme, and is covered by unit
tests (form encoding, signature verification against hand-built payloads), but has not been exercised
against a live Stripe account.
"""
import hashlib
import hmac
import json
import time

from app.config import stripe_secret_key, stripe_webhook_secret
from app.live.http import client

API = "https://api.stripe.com/v1"


def enabled() -> bool:
    return stripe_secret_key() is not None


def _form(params: dict, prefix: str = "") -> dict:
    """Flatten a nested dict/list into Stripe's bracket form encoding: {'a': {'b': 1}} -> {'a[b]': 1}."""
    out: dict = {}
    for k, v in params.items():
        key = f"{prefix}[{k}]" if prefix else str(k)
        if isinstance(v, dict):
            out.update(_form(v, key))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                out.update(_form(item, f"{key}[{i}]") if isinstance(item, dict) else {f"{key}[{i}]": item})
        elif v is not None:
            out[key] = v
    return out


def create_checkout_session(product_name: str, description: str, amount_cents: int, currency: str,
                             success_url: str, cancel_url: str, metadata: dict) -> dict:
    """A hosted Stripe Checkout page for one payment. We never see or store a card number."""
    body = _form({
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "line_items": [{"quantity": 1, "price_data": {
            "currency": currency, "unit_amount": amount_cents,
            "product_data": {"name": product_name, "description": description},
        }}],
        "metadata": metadata,
    })
    with client(20) as c:
        r = c.post(f"{API}/checkout/sessions", data=body, headers={"Authorization": f"Bearer {stripe_secret_key()}"})
        r.raise_for_status()
        return r.json()


def verify_webhook(payload: bytes, sig_header: str, tolerance: int = 300, now: float | None = None) -> dict | None:
    """Verify Stripe's webhook signature and return the parsed event, or None if it is missing, wrong, too
    old, or webhooks are not configured. Manual HMAC-SHA256 check per Stripe's documented scheme (no SDK):
    the header is 't=<unix time>,v1=<hex hmac of "<t>.<payload>" with the webhook secret>'."""
    secret = stripe_webhook_secret()
    if not secret or not sig_header:
        return None
    parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
    ts, sig = parts.get("t"), parts.get("v1")
    if not ts or not sig:
        return None
    try:
        if abs((now if now is not None else time.time()) - float(ts)) > tolerance:
            return None
    except ValueError:
        return None
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        return json.loads(payload)
    except ValueError:
        return None
