"""Partner portal, moderation, ranking, feed, and the Ticketmaster/Travelpayouts parsers. No network."""
import itertools
from pathlib import Path
from datetime import date, timedelta

import pytest

from app.partners import activity, deals, security
from app.suppliers import ticketmaster, travelpayouts

ADMIN = {"X-Admin-Token": "test-admin-token-1234567890"}
_n = itertools.count(1)


@pytest.fixture(autouse=True)
def fresh_limits(tmp_path, monkeypatch):
    security.reset_limits()
    monkeypatch.setattr(activity, "LOG_PATH", tmp_path / "partner-activity.md")  # never touch the real log


def deal_body(**over):
    today = date.today()
    body = {
        "title": "Two-course dinner with wine", "description": "A two-course tasting dinner with a glass of house wine.",
        "category": "restaurant", "dest": "OPO", "address": "Rua das Flores 10", "lat": 41.1450, "lng": -8.6120,
        "price": 24.0, "reference_price": 40.0, "currency": "EUR", "price_note": "per person",
        "valid_from": today.isoformat(), "valid_to": (today + timedelta(days=30)).isoformat(),
        "url": "https://example.com/book", "terms": "Tuesday to Thursday only. Booking required.",
    }
    body.update(over)
    return body


def signup(client, name="Tasca do Rio", email=None):
    email = email or f"owner{next(_n)}@example.com"
    r = client.post("/api/partners/register", json={
        "name": name, "email": email, "password": "correct-horse-battery", "business_type": "restaurant", "city": "OPO"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}, email


def submit(client, headers, **over):
    r = client.post("/api/partners/deals", json=deal_body(**over), headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def approve(client, deal_id):
    assert client.post(f"/api/admin/deals/{deal_id}/approve", headers=ADMIN).status_code == 200


def city_deals(client, **params):
    return client.get("/api/deals", params={"dest": "OPO", **params}).json()["deals"]


# ---------------------------------------------------------------- accounts

def test_register_login_and_me(client):
    headers, email = signup(client)
    me = client.get("/api/partners/me", headers=headers).json()
    assert me["partner"]["email"] == email and me["totals"]["deals"] == 0
    login = client.post("/api/partners/login", json={"email": email.upper(), "password": "correct-horse-battery"})
    assert login.status_code == 200 and login.json()["token"]


def test_password_is_stored_hashed_and_wrong_password_rejected(client):
    _, email = signup(client)
    assert client.post("/api/partners/login", json={"email": email, "password": "wrong-password-1"}).status_code == 401
    assert client.post("/api/partners/login", json={"email": "nobody@example.com", "password": "whatever-1234"}).status_code == 401
    stored = security.hash_password("correct-horse-battery")
    assert stored.startswith("scrypt$") and "correct-horse" not in stored
    assert security.verify_password("correct-horse-battery", stored) and not security.verify_password("nope", stored)


def test_register_validation_and_duplicate(client):
    _, email = signup(client)
    base = {"name": "X Bar", "email": email, "password": "correct-horse-battery", "business_type": "bar", "city": "OPO"}
    assert client.post("/api/partners/register", json=base).status_code == 409
    assert client.post("/api/partners/register", json={**base, "email": "new1@example.com", "password": "short"}).status_code == 400
    assert client.post("/api/partners/register", json={**base, "email": "not-an-email"}).status_code == 400
    assert client.post("/api/partners/register", json={**base, "email": "new2@example.com", "city": "Atlantis"}).status_code == 400


def test_a_commonly_leaked_password_is_refused_even_though_it_is_long_enough(client):
    r = client.post("/api/partners/register", json={"name": "X Bar", "email": "weakpw@example.com", "password": "administrator", "business_type": "bar", "city": "OPO"})
    assert r.status_code == 400 and "common" in r.json()["detail"].lower()


def test_login_is_rate_limited_per_account_across_different_addresses(client):
    _, email = signup(client)
    for _ in range(8):
        client.post("/api/partners/login", json={"email": email, "password": "wrong-password-1"})
    r = client.post("/api/partners/login", json={"email": email, "password": "correct-horse-battery"})
    assert r.status_code == 429


def test_changing_my_password_signs_out_every_session_and_the_new_password_works(client):
    h, email = signup(client)
    other_session = client.post("/api/partners/login", json={"email": email, "password": "correct-horse-battery"}).json()["token"]
    assert client.post("/api/partners/change-password", json={"current_password": "wrong", "new_password": "a-new-password-1"}, headers=h).status_code == 401
    assert client.post("/api/partners/change-password", json={"current_password": "correct-horse-battery", "new_password": "short"}, headers=h).status_code == 400
    r = client.post("/api/partners/change-password", json={"current_password": "correct-horse-battery", "new_password": "a-new-password-1"}, headers=h)
    assert r.status_code == 200
    assert client.get("/api/partners/me", headers=h).status_code == 401
    assert client.get("/api/partners/me", headers={"Authorization": f"Bearer {other_session}"}).status_code == 401
    assert client.post("/api/partners/login", json={"email": email, "password": "correct-horse-battery"}).status_code == 401
    assert client.post("/api/partners/login", json={"email": email, "password": "a-new-password-1"}).status_code == 200


def test_portal_endpoints_need_a_session(client):
    assert client.get("/api/partners/me").status_code == 401
    assert client.post("/api/partners/deals", json=deal_body()).status_code == 401
    assert client.get("/api/partners/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_logout_ends_the_session(client):
    headers, _ = signup(client)
    client.post("/api/partners/logout", headers=headers)
    assert client.get("/api/partners/me", headers=headers).status_code == 401


def test_login_is_rate_limited(client):
    statuses = [client.post("/api/partners/login", json={"email": "a@example.com", "password": "wrong-password-1"}).status_code for _ in range(17)]
    assert statuses[0] == 401 and statuses[-1] == 429


# ---------------------------------------------------------------- deal validation

@pytest.mark.parametrize("change,fragment", [
    ({"reference_price": 20.0}, "usual price must be higher"),
    ({"price": 2.0, "reference_price": 100.0}, "look like a mistake"),
    ({"valid_to": (date.today() - timedelta(days=1)).isoformat()}, "in the past"),
    ({"valid_to": (date.today() + timedelta(days=500)).isoformat()}, "at most a year"),
    ({"url": "http://example.com/x"}, "https://"),
    ({"photo_url": "javascript:alert(1)"}, "https://"),
    ({"lat": None, "lng": None}, "location"),
    ({"lat": 48.85, "lng": 2.35}, "40 km"),
    ({"dest": "Atlantis"}, "destinations"),
    ({"tags": ["not-a-tag"]}, "Unknown tag"),
])
def test_invalid_deals_are_rejected_with_a_clear_reason(client, change, fragment):
    headers, _ = signup(client)
    r = client.post("/api/partners/deals", json=deal_body(**change), headers=headers)
    assert r.status_code == 422 and fragment in str(r.json()), r.text


def test_flights_need_no_location(client):
    headers, _ = signup(client)
    submit(client, headers, category="flight", lat=None, lng=None, title="London to Porto from 39 euro")


# ---------------------------------------------------------------- moderation

def test_new_deals_are_hidden_until_approved_and_rejection_is_explained(client):
    headers, _ = signup(client, name="Hidden Bistro")
    a, b = submit(client, headers, title="Deal that will be approved"), submit(client, headers, title="Deal that will be rejected")
    assert not [d for d in city_deals(client) if d["id"] in (a, b)]

    pend = {d["id"]: d for d in client.get("/api/admin/deals", headers=ADMIN).json()["deals"]}
    assert a in pend and "No photo" in pend[a]["flags"]
    approve(client, a)
    assert client.post(f"/api/admin/deals/{b}/reject", json={"reason": "no"}, headers=ADMIN).status_code == 422
    assert client.post(f"/api/admin/deals/{b}/reject", json={"reason": "Usual price not credible"}, headers=ADMIN).status_code == 200

    live = {d["id"] for d in city_deals(client)}
    assert a in live and b not in live
    mine = {d["id"]: d for d in client.get("/api/partners/me", headers=headers).json()["deals"]}
    assert mine[a]["status"] == "approved" and mine[b]["reject_reason"] == "Usual price not credible"


def test_admin_endpoints_need_the_admin_token(client):
    assert client.get("/api/admin/deals").status_code == 401
    assert client.get("/api/admin/deals", headers={"X-Admin-Token": "wrong"}).status_code == 401
    headers, _ = signup(client)
    assert client.get("/api/admin/deals", headers=headers).status_code == 401  # a partner session is not admin


def test_admin_is_disabled_when_no_token_is_configured(client, monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN")
    assert client.get("/api/admin/deals", headers=ADMIN).status_code == 503


def test_editing_an_approved_deal_sends_it_back_to_review_but_identical_content_does_not(client):
    headers, _ = signup(client)
    did = submit(client, headers, title="Editable deal one")
    approve(client, did)
    assert client.put(f"/api/partners/deals/{did}", json=deal_body(title="Editable deal one"), headers=headers).status_code == 200
    assert did in {d["id"] for d in city_deals(client)}  # unchanged content stays live
    assert client.put(f"/api/partners/deals/{did}", json=deal_body(title="Editable deal one", price=20.0), headers=headers).status_code == 200
    assert did not in {d["id"] for d in city_deals(client)}  # changed content is pending again


def test_pause_end_and_ownership(client):
    headers, _ = signup(client)
    other, _ = signup(client)
    did = submit(client, headers, title="Pausable deal here")
    approve(client, did)
    assert client.post(f"/api/partners/deals/{did}/pause", json={"paused": True}, headers=other).status_code == 404
    assert client.post(f"/api/partners/deals/{did}/pause", json={"paused": True}, headers=headers).status_code == 200
    assert did not in {d["id"] for d in city_deals(client)}
    client.post(f"/api/partners/deals/{did}/pause", json={"paused": False}, headers=headers)
    assert did in {d["id"] for d in city_deals(client)}
    assert client.delete(f"/api/partners/deals/{did}", headers=other).status_code == 404
    assert client.delete(f"/api/partners/deals/{did}", headers=headers).status_code == 200
    assert did not in {d["id"] for d in city_deals(client)}


def test_suspending_a_partner_hides_their_deals_and_blocks_login(client):
    headers, email = signup(client, name="Soon Suspended")
    did = submit(client, headers, title="Deal from suspended")
    approve(client, did)
    pid = client.get("/api/partners/me", headers=headers).json()["partner"]["id"]
    assert client.post(f"/api/admin/partners/{pid}/status", json={"status": "suspended"}, headers=ADMIN).status_code == 200
    assert did not in {d["id"] for d in city_deals(client)}
    assert client.get("/api/partners/me", headers=headers).status_code == 401
    assert client.post("/api/partners/login", json={"email": email, "password": "correct-horse-battery"}).status_code == 403


def test_expired_and_future_deals_are_not_shown(client):
    headers, _ = signup(client)
    future = submit(client, headers, title="Starts next month", valid_from=(date.today() + timedelta(days=20)).isoformat(),
                    valid_to=(date.today() + timedelta(days=40)).isoformat())
    approve(client, future)
    assert future not in {d["id"] for d in city_deals(client)}
    window = city_deals(client, start=(date.today() + timedelta(days=25)).isoformat(), end=(date.today() + timedelta(days=27)).isoformat())
    assert future in {d["id"] for d in window}  # shown for a trip that overlaps its dates


# ---------------------------------------------------------------- tracking

def test_impressions_and_clicks_are_counted_for_the_owner(client):
    headers, _ = signup(client)
    did = submit(client, headers, title="Counted deal number one")
    approve(client, did)
    city_deals(client)
    city_deals(client)
    assert client.post(f"/api/deals/{did}/click").status_code == 200
    mine = next(d for d in client.get("/api/partners/me", headers=headers).json()["deals"] if d["id"] == did)
    assert mine["impressions"] == 2 and mine["clicks"] == 1
    assert client.post("/api/deals/999999/click").status_code == 404


# ---------------------------------------------------------------- ranking

def _d(id_, tags=(), category="hotel", pct=0, **extra):
    return {"id": id_, "tags": list(tags), "category": category, "discount_pct": pct, "lat": None, "lng": None, **extra}


def test_ranking_prefers_interest_match_and_real_discounts():
    ranked = deals.rank_deals([_d(1), _d(2, pct=20), _d(3, category="bar")], ["nightlife"])
    assert [d["id"] for d in ranked][0] == 3 and ranked[0]["match"] == ["nightlife"]
    assert ranked[1]["id"] == 2 and "20% below the usual price" in ranked[1]["why"]


def test_ranking_cannot_be_bought():
    """Whatever a deal says about who the partner is or what they pay, the order does not change."""
    plain = [_d(1), _d(2, pct=20), _d(3, category="restaurant")]
    dressed = [{**d, "paid": True, "tier": "platinum", "sponsored": True, "partner_name": "Big Chain", "boost": 99} for d in plain[:1]] + plain[1:]
    assert [d["id"] for d in deals.rank_deals(plain, ["food-scene"])] == [d["id"] for d in deals.rank_deals(dressed, ["food-scene"])]


def test_every_public_deal_is_labelled_as_a_partner_deal(client):
    headers, _ = signup(client)
    did = submit(client, headers, title="Labelled deal number one")
    approve(client, did)
    body = client.get("/api/deals", params={"dest": "OPO"}).json()
    assert body["deals"] and all(d["partner"] is True for d in body["deals"]) and "never by who pays" in body["disclosure"]


# ---------------------------------------------------------------- feed

def test_partner_feed_needs_a_key_and_is_moderated(client):
    headers, _ = signup(client)
    assert client.post("/api/partner-feed", json={"deals": []}).status_code == 401
    assert client.post("/api/partner-feed", json={"deals": []}, headers={"X-API-Key": "wfk_nope"}).status_code == 401

    key = client.post("/api/partners/api-key", headers=headers).json()["api_key"]
    good = deal_body(external_id="menu-1", title="Feed deal number one")
    bad = deal_body(external_id="menu-2", reference_price=1.0)
    no_id = deal_body(title="Feed deal without id")
    res = client.post("/api/partner-feed", json={"deals": [good, bad, no_id]}, headers={"X-API-Key": key}).json()["results"]
    assert [r["result"] for r in res] == ["created", "rejected", "rejected"]
    assert not [d for d in city_deals(client) if d["id"] == res[0]["id"]]  # pending until reviewed

    approve(client, res[0]["id"])
    again = client.post("/api/partner-feed", json={"deals": [good]}, headers={"X-API-Key": key}).json()["results"]
    assert again[0]["result"] == "updated" and again[0]["id"] == res[0]["id"]
    assert res[0]["id"] in {d["id"] for d in city_deals(client)}  # identical resend keeps it live

    new_key = client.post("/api/partners/api-key", headers=headers).json()["api_key"]
    assert client.post("/api/partner-feed", json={"deals": []}, headers={"X-API-Key": key}).status_code == 401
    assert client.post("/api/partner-feed", json={"deals": []}, headers={"X-API-Key": new_key}).status_code == 200


# ---------------------------------------------------------------- trip and nearby integration

def test_plan_trip_includes_matching_partner_deals(client):
    headers, _ = signup(client, name="Trip Deals Bar")
    did = submit(client, headers, title="Port wine flight tasting", category="bar", tags=["nightlife"])
    approve(client, did)
    start = date.today() + timedelta(days=5)
    res = client.post("/api/plan-trip", json={
        "origin": "LON", "destination": "OPO", "start_date": start.isoformat(),
        "end_date": (start + timedelta(days=4)).isoformat(), "budget": 1500, "travelers": 2, "interests": ["nightlife"],
    })
    assert res.status_code == 200
    found = res.json()["itinerary"]["partner_deals"]
    assert did in [d["id"] for d in found] and found[0]["match"] == ["nightlife"] and found[0]["partner"] is True


def test_nearby_offline_still_returns_partner_deals(client):
    headers, _ = signup(client, name="Nearby Cafe")
    did = submit(client, headers, title="Coffee and pastel de nata", category="restaurant", lat=41.1580, lng=-8.6290)
    approve(client, did)
    res = client.post("/api/nearby", json={"lat": 41.1579, "lng": -8.6291, "interests": ["food-scene"]}).json()
    rec = next(r for r in res["recommendations"] if r["id"] == f"deal-{did}")
    assert rec["kind"] == "deal" and rec["partner"] is True and "DYN-11" in rec["rules"] and "DYN-07" in rec["rules"]
    far = client.post("/api/nearby", json={"lat": 41.20, "lng": -8.62, "interests": []}).json()
    assert not [r for r in far["recommendations"] if r["id"] == f"deal-{did}"]


def test_events_report_disabled_without_a_key(client):
    body = client.get("/api/events", params={"dest": "OPO"}).json()
    assert body["enabled"] is False and body["events"] == []
    assert client.get("/api/events", params={"dest": "Atlantis"}).status_code == 404
    assert client.get("/api/config").json()["ticketmaster"] is False


# ---------------------------------------------------------------- supplier parsers

TM_SAMPLE = {"_embedded": {"events": [
    {"id": "Z1", "name": "Fado Night", "url": "https://www.ticketmaster.example/e/Z1",
     "images": [{"url": "https://img/a.jpg", "ratio": "3_2", "width": 300}, {"url": "https://img/b.jpg", "ratio": "16_9", "width": 640}],
     "dates": {"start": {"localDate": "2026-12-05", "localTime": "21:30:00"}},
     "classifications": [{"segment": {"name": "Music"}}], "priceRanges": [{"min": 18.0, "max": 45.0, "currency": "EUR"}],
     "_embedded": {"venues": [{"name": "Coliseu", "location": {"latitude": "41.1467", "longitude": "-8.6106"}}]}},
    {"id": "Z2", "name": "No date", "url": "https://x", "dates": {"start": {}}},
]}}


def test_ticketmaster_parser():
    events = ticketmaster.parse_events(TM_SAMPLE)
    assert len(events) == 1
    e = events[0]
    assert (e["id"], e["title"], e["venue"], e["category"], e["date"], e["time"]) == ("tm-Z1", "Fado Night", "Coliseu", "Music", "2026-12-05", "21:30")
    assert e["photo_url"] == "https://img/b.jpg" and e["price_min"] == 18.0 and (e["lat"], e["lng"]) == (41.1467, -8.6106)
    assert ticketmaster.parse_events({}) == []


def test_travelpayouts_parser():
    data = {"currency": "gbp", "data": [
        {"price": 84, "airline": "TP", "transfers": 0, "duration_to": 145, "departure_at": "2026-12-05T07:15:00+00:00"},
        {"price": 0, "airline": "XX"},
    ]}
    out = travelpayouts.parse_fares(data, "LON", "OPO", "2026-12-05", "2026-12-09", 2)
    assert len(out) == 1
    f = out[0]
    assert (f["price_per_traveler"], f["total_price"], f["currency"], f["price_source"], f["depart_time"]) == (84, 168, "GBP", "travelpayouts", "07:15")
    assert f["airline"] == "TP" and f["stops"] == 0 and f["duration_minutes"] == 145


def test_suppliers_are_off_without_keys():
    assert not ticketmaster.enabled() and not travelpayouts.enabled()


# ---------------------------------------------------------------- runtime log

def test_partner_activity_is_logged_without_personal_data(client):
    headers, email = signup(client, name="Private Name Bistro")
    did = submit(client, headers, title="Logged deal number one")
    approve(client, did)
    client.post(f"/api/partners/deals/{did}/pause", json={"paused": True}, headers=headers)
    log = activity.LOG_PATH.read_text(encoding="utf-8")
    for event in ("partner.registered", "deal.submitted", "deal.approved", "deal.paused"):
        assert event in log
    assert f"deal {did}" in log and "category restaurant" in log
    assert email not in log and "Private Name" not in log and "41.14" not in log


def test_every_logged_event_is_documented():
    docs = (Path(__file__).resolve().parents[2] / "docs" / "FEATURES.md").read_text(encoding="utf-8")
    missing = [e for e in activity.EVENTS if f"`{e}`" not in docs]
    assert not missing, f"Add these events to the partner activity log table in docs/FEATURES.md: {missing}"
