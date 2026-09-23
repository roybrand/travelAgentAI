"""Featured deal placements: Stripe Checkout integration and webhook signature verification. No network --
the Stripe HTTP call itself is monkeypatched at the module boundary, the same way the rest of this suite
never touches the network."""
import hashlib
import hmac
import json
import time

from app.partners import featured, stripe_gateway
from tests.test_partners import ADMIN, approve, city_deals, fresh_limits, signup, submit  # noqa: F401


def sign(secret: str, payload: bytes, ts: int | None = None) -> str:
    ts = ts if ts is not None else int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


# ---------------------------------------------------------------- stripe_gateway: pure functions, no network

def test_form_encoding_flattens_nested_dicts_and_lists():
    out = stripe_gateway._form({"mode": "payment", "metadata": {"deal_id": 1}, "line_items": [{"quantity": 1, "price_data": {"currency": "usd"}}]})
    assert out == {"mode": "payment", "metadata[deal_id]": 1, "line_items[0][quantity]": 1, "line_items[0][price_data][currency]": "usd"}


def test_webhook_signature_is_verified_correctly(monkeypatch):
    monkeypatch.setattr(stripe_gateway, "stripe_webhook_secret", lambda: "whsec_test123")
    payload = json.dumps({"type": "checkout.session.completed", "data": {"object": {"id": "cs_1"}}}).encode()
    good = sign("whsec_test123", payload)
    assert stripe_gateway.verify_webhook(payload, good)["type"] == "checkout.session.completed"
    assert stripe_gateway.verify_webhook(payload, sign("wrong-secret", payload)) is None          # tampered secret
    assert stripe_gateway.verify_webhook(payload + b"x", good) is None                             # tampered body
    assert stripe_gateway.verify_webhook(payload, "not-a-valid-header") is None
    assert stripe_gateway.verify_webhook(payload, "") is None
    old = sign("whsec_test123", payload, ts=int(time.time()) - 10_000)
    assert stripe_gateway.verify_webhook(payload, old) is None                                     # too old


def test_webhook_verification_is_off_without_a_configured_secret(monkeypatch):
    monkeypatch.setattr(stripe_gateway, "stripe_webhook_secret", lambda: None)
    payload = json.dumps({"type": "x"}).encode()
    assert stripe_gateway.verify_webhook(payload, sign("whatever", payload)) is None


# ---------------------------------------------------------------- featured: business logic, DB-level

def fake_session(url="https://checkout.stripe.com/pay/cs_test_1"):
    return {"id": "cs_test_1", "url": url}


def test_payments_are_off_by_default(client):
    h, _ = signup(client)
    did = submit(client, h)
    approve(client, did)
    r = client.post(f"/api/partners/deals/{did}/feature", json={"success_url": "https://x.example/ok", "cancel_url": "https://x.example/no"}, headers=h)
    assert r.status_code == 503


def test_only_my_own_approved_deal_can_be_featured(client, monkeypatch):
    monkeypatch.setattr(stripe_gateway, "enabled", lambda: True)
    monkeypatch.setattr(stripe_gateway, "create_checkout_session", lambda **kw: fake_session())
    h, _ = signup(client)
    pending_id = submit(client, h)  # not yet approved
    r = client.post(f"/api/partners/deals/{pending_id}/feature", json={"success_url": "https://x.example/ok", "cancel_url": "https://x.example/no"}, headers=h)
    assert r.status_code == 404
    other_h, _ = signup(client, email="rival@example.com")
    other_id = submit(client, other_h)
    approve(client, other_id)
    r = client.post(f"/api/partners/deals/{other_id}/feature", json={"success_url": "https://x.example/ok", "cancel_url": "https://x.example/no"}, headers=h)
    assert r.status_code == 404  # not mine


def test_redirect_urls_must_be_https(client, monkeypatch):
    monkeypatch.setattr(stripe_gateway, "enabled", lambda: True)
    monkeypatch.setattr(stripe_gateway, "create_checkout_session", lambda **kw: fake_session())
    h, _ = signup(client)
    did = submit(client, h)
    approve(client, did)
    r = client.post(f"/api/partners/deals/{did}/feature", json={"success_url": "javascript:alert(1)", "cancel_url": "https://x.example/no"}, headers=h)
    assert r.status_code == 422


def test_the_full_checkout_to_featured_strip_flow(client, monkeypatch):
    monkeypatch.setattr(stripe_gateway, "enabled", lambda: True)
    monkeypatch.setattr(stripe_gateway, "create_checkout_session", lambda **kw: fake_session())
    monkeypatch.setattr(stripe_gateway, "stripe_webhook_secret", lambda: "whsec_test123")
    h, _ = signup(client)
    did = submit(client, h)
    approve(client, did)

    assert client.get("/api/deals/featured", params={"dest": "OPO"}).json()["deals"] == []

    r = client.post(f"/api/partners/deals/{did}/feature", json={"success_url": "https://x.example/ok", "cancel_url": "https://x.example/no"}, headers=h)
    assert r.status_code == 200 and r.json()["checkout_url"] == fake_session()["url"]
    # not featured until the webhook confirms payment
    assert client.get("/api/deals/featured", params={"dest": "OPO"}).json()["deals"] == []
    assert client.get("/api/partners/me", headers=h).json()["featured"] == {}

    payload = json.dumps({"type": "checkout.session.completed", "data": {"object": {"id": "cs_test_1", "metadata": {"deal_id": did}}}}).encode()
    wh = client.post("/api/payments/stripe/webhook", content=payload, headers={"stripe-signature": sign("whsec_test123", payload)})
    assert wh.status_code == 200 and wh.json()["received"] is True

    listed = client.get("/api/deals/featured", params={"dest": "OPO"}).json()["deals"]
    assert any(d["id"] == did and d["featured"] is True for d in listed)
    assert str(did) in {str(k) for k in client.get("/api/partners/me", headers=h).json()["featured"]}
    # the payment-blind ranked list is unaffected: rank_deals never sees the featured table
    ranked = {d["id"]: d for d in city_deals(client)}
    assert did in ranked and "featured" not in ranked[did]

    # a retried webhook delivery (Stripe does this) is a no-op the second time
    wh2 = client.post("/api/payments/stripe/webhook", content=payload, headers={"stripe-signature": sign("whsec_test123", payload)})
    assert wh2.status_code == 200
    assert len(client.get("/api/deals/featured", params={"dest": "OPO"}).json()["deals"]) == 1


def test_webhook_rejects_a_bad_signature(client, monkeypatch):
    monkeypatch.setattr(stripe_gateway, "stripe_webhook_secret", lambda: "whsec_test123")
    payload = json.dumps({"type": "checkout.session.completed", "data": {"object": {"id": "cs_x"}}}).encode()
    r = client.post("/api/payments/stripe/webhook", content=payload, headers={"stripe-signature": "t=1,v1=deadbeef"})
    assert r.status_code == 400


def test_mark_paid_ignores_an_unknown_session():
    assert featured.mark_paid("cs_does_not_exist") is False
