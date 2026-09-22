"""The labelled pool of 100 demo travelers: seeding, avatars, daily requests, dynamic matching, automated chat. No network."""
import json
from collections import Counter
from datetime import date

import pytest

from app.live import catalog
from app.partners import db
from app.social import avatars, demo_people, users
from tests.test_partners import fresh_limits  # noqa: F401  (autouse: resets rate limits, temp activity log)
from tests.test_people import ids, looking, person, signup  # noqa: F401

CENTRES = {c: (catalog.BY_CODE[c]["lat"], catalog.BY_CODE[c]["lng"]) for c in demo_people.CITIES}


@pytest.fixture(autouse=True)
def demo_pool(monkeypatch):
    """A fresh pool for every test, with no internet: venues are a fixed list instead of OpenStreetMap."""
    monkeypatch.setattr(demo_people, "_venues", lambda city, arch: [
        {"id": f"osm-node-{i}", "name": f"Venue {i}", "type": "nightclub", "lat": catalog.BY_CODE[city]["lat"] + 0.001 * i, "lng": catalog.BY_CODE[city]["lng"]}
        for i in range(1, 6)])
    with db.tx() as c:
        c.execute("DELETE FROM users")
    demo_people.seed(100)
    yield
    with db.tx() as c:
        c.execute("DELETE FROM users")


def demo_rows():
    with db.tx() as c:
        return c.execute("SELECT * FROM users WHERE demo = 1").fetchall()


# ---------------------------------------------------------------- the static pool

def test_there_are_100_demo_profiles_twenty_in_each_city_and_seeding_twice_adds_none():
    rows = demo_rows()
    assert len(rows) == 100 and Counter(demo_people.city_of(r) for r in rows) == {c: 20 for c in demo_people.CITIES}
    demo_people.seed(100)
    assert len(demo_rows()) == 100
    assert len({r["email"] for r in rows}) == 100 and all(r["email"].endswith("@wayfinder.invalid") for r in rows)


def test_the_pool_covers_all_ages_genders_and_the_world():
    rows = demo_rows()
    assert set(Counter(users.band_of(r) for r in rows)) == set(vocab_bands())
    genders = Counter(r["gender"] for r in rows)
    assert genders["woman"] >= 35 and genders["man"] >= 35 and genders["non-binary"] >= 3 and genders[None] >= 1   # some choose not to say
    assert len({r["home_city"] for r in rows}) >= 20
    for city in demo_people.CITIES:                                    # every city has a spread, not just one kind of person
        here = [r for r in rows if demo_people.city_of(r) == city]
        assert len({users.band_of(r) for r in here}) >= 3 and len({r["gender"] for r in here}) >= 2


def vocab_bands():
    from app.social import vocab
    return vocab.AGE_BANDS


def test_profiles_are_complete_and_always_labelled_demo():
    for r in demo_rows():
        card = users.card(r)
        assert card["demo"] is True and card["bio"] and "None" not in card["bio"] and len(card["bio"]) <= 280
        assert 2 <= len(card["interests"]) <= 5 and card["languages"] and card["photo_url"] == f"/api/people/demo-avatar/{r['id']}"
        assert users.band_of(r) is not None and r["birth_year"] <= date.today().year - 18


def test_everyone_has_a_request_for_today_or_tomorrow_and_the_night_crowd_is_on_real_venue_ids():
    with db.tx() as c:
        open_by_user = Counter(r["user_id"] for r in c.execute("SELECT user_id FROM intents WHERE status = 'open' AND day >= ?", (date.today().isoformat(),)))
        going = c.execute("SELECT COUNT(*) FROM attendances WHERE place_key LIKE 'osm-node-%'").fetchone()[0]
    assert set(open_by_user) == {r["id"] for r in demo_rows()} and going >= 15


def test_daily_refresh_gives_new_requests_only_to_people_without_one():
    assert demo_people.refresh_pool(force=True) == 0                    # everyone already has one
    with db.tx() as c:
        c.execute("UPDATE intents SET status = 'closed' WHERE user_id IN (SELECT id FROM users WHERE demo = 1 LIMIT 10)")
    assert demo_people.refresh_pool(force=True) == 10
    assert demo_people.refresh_pool() == 0                              # rate limited to once an hour


# ---------------------------------------------------------------- avatars

def test_avatars_are_deterministic_varied_safe_drawings():
    assert avatars.avatar_svg(5, "woman") == avatars.avatar_svg(5, "woman")
    assert len({avatars.avatar_svg(i, "man") for i in range(30)}) == 30
    for i in range(40):
        svg = avatars.avatar_svg(i, ["woman", "man", "non-binary", None][i % 4])
        assert svg.startswith("<svg") and svg.endswith("</svg>") and "<script" not in svg and "onload" not in svg
        assert svg.count("http") == 1                                    # only the SVG namespace, no external references


def test_avatar_endpoint_serves_demo_drawings_only(client):
    demo_id = demo_rows()[0]["id"]
    r = client.get(f"/api/people/demo-avatar/{demo_id}")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml") and "default-src 'none'" in r.headers["content-security-policy"]
    real, uid, _ = person(client, "Real Person")
    assert client.get(f"/api/people/demo-avatar/{uid}").status_code == 404    # a real person never gets a drawing standing in for them
    assert client.get("/api/people/demo-avatar/999999").status_code == 404


def test_an_ai_portrait_is_served_when_one_exists_and_the_drawing_otherwise(client):
    demo_id = demo_rows()[1]["id"]
    d = demo_people.portrait_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{demo_id}.webp").write_bytes(b"RIFF\x00\x00\x00\x00WEBPfake")
    try:
        r = client.get(f"/api/people/demo-avatar/{demo_id}")
        assert r.status_code == 200 and r.headers["content-type"] == "image/webp" and r.content.startswith(b"RIFF")
        assert client.get(f"/api/people/demo-avatar/{demo_rows()[2]['id']}").headers["content-type"].startswith("image/svg+xml")
    finally:
        (d / f"{demo_id}.webp").unlink()


# ---------------------------------------------------------------- matching with a real person

def real_search(client, text, city, **extra):
    h, uid, _ = person(client, f"Real {city}", interests=("nightlife", "live-music", "coffee"))
    lat, lng = CENTRES[city]
    body = {"text": text, "lat": lat, "lng": lng, "radius_m": 5000, **extra}
    return h, uid, client.post("/api/people/looking", json=body, headers=h).json()


def test_the_static_pool_already_has_people_for_tonight_in_every_city(client, monkeypatch):
    monkeypatch.setattr(demo_people, "attune", lambda *a, **k: 0)         # no dynamic help: only the seeded requests
    for city in demo_people.CITIES:
        _, _, res = real_search(client, "Coffee, drinks or live music tonight", city)
        assert res["people"] and all(p["demo"] for p in res["people"]), city


def test_dynamic_matching_brings_fitting_demo_people_in_every_city(client):
    for city in demo_people.CITIES:
        _, uid, res = real_search(client, "Live music tonight", city)
        assert len(res["people"]) >= 3 and all(p["demo"] and "live-music" in p["shared"] for p in res["people"][:3]), city
        assert all(p["distance"] for p in res["people"]) and "lat" not in json.dumps(res["people"])


def test_dynamic_matches_respect_gender_and_age_filters(client):
    _, _, women = real_search(client, "Coffee tonight with women", "BCN")
    assert women["people"] and {p["gender"] for p in women["people"]} == {"woman"}
    _, _, older = real_search(client, "Coffee tonight for people aged 45-54", "PAR")
    assert older["people"]
    with db.tx() as c:
        bands = {users.band_of(c.execute("SELECT * FROM users WHERE id = ?", (p["id"],)).fetchone()) for p in older["people"]}
    assert bands == {"45-54"}
    _, _, none = real_search(client, "Coffee tonight", "BER", want_genders=["non-binary"], want_ages=["55+"])
    assert all(p["gender"] == "non-binary" for p in none["people"])


def test_a_request_far_from_the_five_cities_gets_no_invented_matches(client):
    h, uid, _ = person(client, "Far away")
    res = client.post("/api/people/looking", json={"text": "Live music tonight", "lat": 41.1579, "lng": -8.6291, "radius_m": 5000}, headers=h).json()   # Porto
    assert res["people"] == []


def test_dynamic_matching_is_repeatable_and_does_not_flood(client):
    h, uid, first = real_search(client, "Live music tonight", "TLV")
    again = client.post("/api/people/looking", json={"text": "Live music tonight", "lat": CENTRES["TLV"][0], "lng": CENTRES["TLV"][1], "radius_m": 5000}, headers=h).json()
    with db.tx() as c:
        assert c.execute("SELECT COUNT(*) FROM intents WHERE status = 'open' AND user_id IN (SELECT id FROM users WHERE demo = 1)").fetchone()[0] <= 100 + 8
    assert ids(first["people"]) and ids(again["people"])


def test_demo_people_do_not_appear_to_people_who_blocked_them(client):
    h, uid, res = real_search(client, "Live music tonight", "IBZ")
    target = res["people"][0]["id"]
    client.post("/api/people/block", json={"user_id": target}, headers=h)
    again = client.post("/api/people/looking", json={"text": "Live music tonight", "lat": CENTRES["IBZ"][0], "lng": CENTRES["IBZ"][1], "radius_m": 5000}, headers=h).json()
    assert target not in ids(again["people"])


# ---------------------------------------------------------------- chatting with a demo person

def test_saying_hi_to_a_demo_person_opens_an_automated_labelled_chat(client):
    h, uid, res = real_search(client, "Live music tonight", "BER")
    demo_id = res["people"][0]["id"]
    r = client.post("/api/people/connect", json={"to_user": demo_id, "message": "Hi! Fancy it?"}, headers=h).json()
    assert r["status"] == "accepted"
    chats = client.get("/api/people/connections", headers=h).json()["chats"]
    assert chats[0]["person"]["demo"] is True
    cid = chats[0]["connection_id"]
    first = client.get(f"/api/people/chats/{cid}/messages", headers=h).json()["messages"]
    assert len(first) == 1 and first[0]["mine"] is False and "Thanks for the request" in first[0]["body"]
    sent = client.post(f"/api/people/chats/{cid}/messages", json={"body": "Around 9 at the club?"}, headers=h)
    assert sent.status_code == 200 and sent.json()["mine"] is True
    msgs = client.get(f"/api/people/chats/{cid}/messages", headers=h).json()["messages"]
    assert [m["mine"] for m in msgs] == [False, True, False] and msgs[2]["body"] in demo_people.REPLIES


def test_removing_the_demo_pool_removes_everything_about_it(client):
    h, uid, res = real_search(client, "Live music tonight", "PAR")
    client.post("/api/people/connect", json={"to_user": res["people"][0]["id"]}, headers=h)
    assert demo_people.remove() == 100
    with db.tx() as c:
        left = [c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("attendances", "messages")]
        real_intents = c.execute("SELECT COUNT(*) FROM intents").fetchone()[0]
    assert left == [0, 0] and real_intents == 1                          # only the real person's own request is left
    assert client.get("/api/people/me", headers=h).status_code == 200   # the real account is untouched
    assert not demo_people.exists()
