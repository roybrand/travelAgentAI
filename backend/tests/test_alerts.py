"""100 demo businesses, the alerts radar (deals, people, requests, messages) and the RSS feed. No network."""
import json
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, timedelta

import pytest

from app.live import catalog
from app.partners import db, deals, demo_businesses
from app.social import demo_people
from tests.test_partners import ADMIN, approve, fresh_limits, signup as partner_signup, submit  # noqa: F401
from tests.test_people import ids, looking, person, PORTO  # noqa: F401

TLV = (catalog.BY_CODE["TLV"]["lat"], catalog.BY_CODE["TLV"]["lng"])
TODAY = date.today()


@pytest.fixture(scope="module", autouse=True)
def business_pool():
    with db.tx() as c:
        c.execute("DELETE FROM partners WHERE email LIKE 'demo-biz-%'")
    demo_businesses.seed(124)
    yield
    demo_businesses.remove()


@pytest.fixture(autouse=True)
def no_people(monkeypatch):
    monkeypatch.setattr(demo_people, "exists", lambda: False)     # this file is about businesses; people alerts use real users
    with db.tx() as c:
        c.execute("DELETE FROM users")


def post(client, headers=None, **ctx):
    return client.post("/api/alerts", json=ctx, headers=headers or {}).json()


# ---------------------------------------------------------------- the 100 businesses

def test_there_are_124_labelled_businesses_across_the_world():
    with db.tx() as c:
        rows = c.execute("SELECT * FROM partners WHERE email LIKE 'demo-biz-%'").fetchall()
    assert len(rows) == 124
    assert all(r["name"].startswith("Demo · ") and r["email"].endswith("@wayfinder.invalid") for r in rows)
    by_city = Counter(r["city"] for r in rows)
    assert {c: by_city[c] for c in ("TLV", "BER", "BCN", "PAR", "IBZ")} == {c: 8 for c in ("TLV", "BER", "BCN", "PAR", "IBZ")}
    assert len(by_city) == 33 and by_city["SYD"] == 3 and all(n == 3 for c, n in by_city.items() if c not in ("TLV", "BER", "BCN", "PAR", "IBZ"))
    assert {r["business_type"] for r in rows} == {"restaurant", "bar", "party", "tour", "activity", "spa", "hotel", "car_rental"}
    demo_businesses.seed(124)
    with db.tx() as c:
        assert c.execute("SELECT COUNT(*) FROM partners WHERE email LIKE 'demo-biz-%'").fetchone()[0] == 124     # seeding twice adds none


def test_every_business_has_a_live_labelled_deal_with_a_drawn_picture(client):
    for city in ("TLV", "BER", "BCN", "PAR", "IBZ", "TYO"):
        found = client.get("/api/deals", params={"dest": city}).json()["deals"]
        demo = [d for d in found if d["partner_name"].startswith("Demo · ")]
        assert len(demo) >= 3 and all(d["partner"] is True and d["photo_url"].startswith("/api/deals/art/") for d in demo), city
    with db.tx() as c:
        live_partners = c.execute("SELECT COUNT(DISTINCT partner_id) FROM deals WHERE status = 'approved' AND valid_to >= ? AND partner_id IN "
                                  "(SELECT id FROM partners WHERE email LIKE 'demo-biz-%')", (TODAY.isoformat(),)).fetchone()[0]
    assert live_partners == 124


def test_art_endpoint_serves_safe_drawings_only(client):
    r = client.get("/api/deals/art/bar/7")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml") and "<script" not in r.text and r.text == client.get("/api/deals/art/bar/7").text
    assert client.get("/api/deals/art/bar/8").text != r.text
    assert client.get("/api/deals/art/not-a-kind/1").status_code == 404 and client.get("/api/deals/art/bar/999999").status_code == 404


def test_daily_refresh_renews_expired_deals_and_posts_flash_deals_once():
    with db.tx() as c:
        flash = c.execute("SELECT COUNT(*) FROM deals WHERE external_id = ?", (f"flash-{TODAY.isoformat()}",)).fetchone()[0]
        row = c.execute("SELECT partner_id FROM deals WHERE external_id IS NULL AND partner_id IN (SELECT id FROM partners WHERE email LIKE 'demo-biz-%') LIMIT 1").fetchone()
        c.execute("UPDATE deals SET valid_to = ? WHERE partner_id = ? AND external_id IS NULL", ((TODAY - timedelta(days=1)).isoformat(), row["partner_id"]))
    assert flash == 30
    assert demo_businesses.refresh(force=True) == 1                       # only the business whose deal ran out gets a new one
    assert demo_businesses.refresh(force=True) == 0
    tomorrow = TODAY + timedelta(days=1)
    assert demo_businesses.refresh(force=True, today=tomorrow) >= 30      # a new day brings new flash deals


# ---------------------------------------------------------------- deal alerts

def test_a_trip_gets_good_deals_for_its_dates_best_match_first(client):
    res = post(client, dest="TLV", start=TODAY.isoformat(), end=(TODAY + timedelta(days=5)).isoformat(), interests=["nightlife"], min_discount=25)
    found = res["alerts"]
    assert found and all(a["kind"] == "deal" and a["deal"]["city"] == "Tel Aviv" for a in found)
    assert all(a["deal"]["discount_pct"] >= 25 or a["hours_left"] is not None for a in found)
    assert any("During your trip to Tel Aviv" in a["reason"] for a in found)
    assert found == sorted(found, key=lambda a: (-a["priority"], -a["score"]))
    top = found[0]
    assert top["title"] and top["badge"].startswith("−") and top["image"].startswith("/api/deals/art/") and top["deal"]["url"].startswith("https://")


def test_interest_matches_are_explained_and_ranked_up(client):
    res = post(client, dest="BCN", interests=["nightlife"], min_discount=10)["alerts"]
    matched = [a for a in res if "Matches what you like" in a["reason"]]
    assert matched and all(a["deal"]["category"] in ("bar", "party") for a in matched)
    assert res.index(matched[0]) <= 2


def test_a_radius_finds_deals_near_a_position_with_distances(client):
    res = post(client, lat=TLV[0], lng=TLV[1], radius_m=5000, min_discount=10)["alerts"]
    assert res and all(a["deal"]["city"] == "Tel Aviv" for a in res)
    assert any(any("km away" in r or " m away" in r for r in a["reason"]) for a in res)
    assert post(client, lat=-33.87, lng=151.21, radius_m=5000, min_discount=0)["alerts"]      # Sydney now has businesses
    assert post(client, lat=64.1, lng=-21.9, radius_m=5000)["alerts"] == []                  # Reykjavik: none


def test_a_higher_bar_shows_fewer_and_hot_deals_are_flagged(client):
    loose = post(client, dest="PAR", min_discount=0)["alerts"]
    strict = post(client, dest="PAR", min_discount=45)["alerts"]
    assert len(strict) <= len(loose) and all(a["deal"]["discount_pct"] >= 45 or a["hours_left"] is not None or "Matches what you like" in a["reason"] for a in strict)
    for a in loose:
        assert a["hot"] == (a["deal"]["discount_pct"] >= 30 or "Ends tonight" in a["reason"])
    tonight = [a for a in loose if a["title"].startswith("Tonight only")]
    assert tonight and all("Ends tonight" in a["reason"] and a["hours_left"] is not None for a in tonight)


def test_nothing_to_go_on_means_no_alerts_and_bad_input_is_refused(client):
    assert post(client)["alerts"] == [] and post(client, dest="Atlantis")["alerts"] == []
    assert client.post("/api/alerts", json={"radius_m": 5}).status_code == 422 and client.post("/api/alerts", json={"min_discount": 200}).status_code == 422


def test_paused_or_suspended_partners_never_alert(client):
    headers, _ = partner_signup(client, name="Gone Soon")
    did = submit(client, headers, title="Half price cocktails for a week", category="bar", dest="IBZ", lat=38.9067, lng=1.4206, price=5.0, reference_price=12.0)
    approve(client, did)
    hit = lambda: any(a["deal"]["id"] == did for a in post(client, dest="IBZ", min_discount=0)["alerts"])
    assert hit()
    pid = client.get("/api/partners/me", headers=headers).json()["partner"]["id"]
    client.post(f"/api/admin/partners/{pid}/status", json={"status": "suspended"}, headers=ADMIN)
    assert not hit()


# ---------------------------------------------------------------- people, requests and messages

def test_signed_in_people_get_match_request_and_message_alerts_with_profiles(client):
    a, a_id, a_email = person(client, "Alma", interests=("live-music",))
    b, b_id, _ = person(client, "Bruno", interests=("live-music",))
    looking(client, b, "Live music tonight, someone relaxed")
    looking(client, a, "Live music tonight")
    res = post(client, headers=a, lat=PORTO[0], lng=PORTO[1])
    match = next(x for x in res["alerts"] if x["kind"] == "person")
    assert match["id"] == f"person-{b_id}" and match["title"] == "Bruno wants the same as you" and match["person"]["id"] == b_id and match["priority"] == 3
    assert match["person"]["display_name"] == "Bruno" and match["reason"]
    assert a_email not in json.dumps(res) and "birth" not in json.dumps(res) and "41.15" not in json.dumps(res["alerts"][0].get("person", {}))
    # Bruno asks to connect: Alma gets a request alert, and Bruno leaves the match list
    cid = client.post("/api/people/connect", json={"to_user": a_id, "message": "Fancy it?"}, headers=b).json()["id"]
    res = post(client, headers=a)
    req = next(x for x in res["alerts"] if x["kind"] == "request")
    assert req["title"] == "Bruno wants to connect" and req["body"] == "“Fancy it?”" and req["connection_id"] == cid and req["link"] == "/people?tab=inbox"
    assert not [x for x in res["alerts"] if x["kind"] == "person"]
    # she says yes, he writes: a message alert with his profile
    client.post(f"/api/people/connections/{cid}/respond", json={"accept": True}, headers=a)
    client.post(f"/api/people/chats/{cid}/messages", json={"body": "Around 9 at the club?"}, headers=b)
    msg = next(x for x in post(client, headers=a)["alerts"] if x["kind"] == "message")
    assert msg["title"] == "New message from Bruno" and msg["body"] == "Around 9 at the club?" and msg["person"]["id"] == b_id
    assert msg["link"] == f"/people?tab=inbox&chat={cid}"
    # her own message is not an alert for her
    client.post(f"/api/people/chats/{cid}/messages", json={"body": "See you there"}, headers=a)
    assert not [x for x in post(client, headers=a)["alerts"] if x["kind"] == "message"]


def test_anonymous_visitors_and_other_people_never_see_someone_elses_alerts(client):
    a, a_id, _ = person(client, "Alma")
    b, b_id, _ = person(client, "Bruno")
    looking(client, a, "Live music tonight")
    client.post("/api/people/connect", json={"to_user": a_id}, headers=b)
    anon = post(client, lat=PORTO[0], lng=PORTO[1])
    assert anon["signed_in"] is False and all(x["kind"] == "deal" for x in anon["alerts"])
    other, _, _ = person(client, "Carla")
    assert not [x for x in post(client, headers=other)["alerts"] if x["kind"] in ("request", "message")]
    assert post(client, headers={"Authorization": "Bearer nonsense"})["signed_in"] is False


def test_blocked_people_do_not_alert_and_kinds_can_be_switched_off(client):
    a, a_id, _ = person(client, "Alma")
    b, b_id, _ = person(client, "Bruno")
    looking(client, b, "Coffee tonight")
    looking(client, a, "Coffee tonight")
    assert [x for x in post(client, headers=a)["alerts"] if x["kind"] == "person"]
    assert not [x for x in post(client, headers=a, kinds=["deal"])["alerts"] if x["kind"] == "person"]
    client.post("/api/people/block", json={"user_id": b_id}, headers=a)
    assert not [x for x in post(client, headers=a)["alerts"] if x["kind"] == "person"]


def test_match_alerts_respect_gender_and_age_filters(client):
    a, a_id, _ = person(client, "Alma")
    w, w_id, _ = person(client, "Wren")
    m, m_id, _ = person(client, "Milo")
    client.patch("/api/people/me", json={"gender": "woman"}, headers=w)
    client.patch("/api/people/me", json={"gender": "man"}, headers=m)
    for h in (w, m):
        looking(client, h, "Coffee tonight")
    client.post("/api/people/looking", json={"text": "Coffee tonight", "lat": PORTO[0], "lng": PORTO[1], "radius_m": 3000, "want_genders": ["woman"]}, headers=a)
    who = {x["person"]["id"] for x in post(client, headers=a)["alerts"] if x["kind"] == "person"}
    assert who == {w_id}


# ---------------------------------------------------------------- RSS

def test_rss_feed_is_valid_and_carries_the_deal_alerts(client):
    r = client.get("/api/feed/deals.xml", params={"dest": "BER", "interests": "nightlife", "min_discount": 10})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/rss+xml")
    root = ET.fromstring(r.text)
    assert root.tag == "rss" and root.find("channel/title").text == "Wayfinder deals in Berlin"
    items = root.findall("channel/item")
    assert items and all(i.find("title").text and i.find("link").text.startswith("http") and i.find("guid").text.startswith("wayfinder-deal-") for i in items)
    assert len(items) == len(post(client, dest="BER", interests=["nightlife"], min_discount=10)["alerts"])
    assert client.get("/api/feed/deals.xml", params={"dest": "Atlantis"}).status_code == 404


def test_rss_escapes_special_characters(client):
    headers, _ = partner_signup(client, name="Fish & Chips <Ltd>")
    did = submit(client, headers, title="Fish & chips <two> for £5", category="restaurant", dest="LON", lat=51.5074, lng=-0.1278, price=5.0, reference_price=12.0)
    approve(client, did)
    r = client.get("/api/feed/deals.xml", params={"dest": "LON", "min_discount": 0})
    root = ET.fromstring(r.text)                                       # would raise if anything were left unescaped
    assert any("Fish & chips <two>" in (i.find("title").text or "") for i in root.findall("channel/item"))
    assert "&amp;" in r.text and "<two>" not in r.text
