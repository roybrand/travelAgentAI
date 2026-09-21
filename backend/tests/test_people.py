"""Wayfinder People: accounts, photos, places, finding people, consent-based chat and safety. No network."""
import base64
import itertools
import json
from datetime import date, timedelta

import pytest

from app.partners import db
from app.social import intents, users, vocab
from tests.test_partners import ADMIN, fresh_limits  # noqa: F401  (autouse fixture: resets rate limits, temp activity log)

@pytest.fixture(autouse=True)
def clean_people():
    """Every test starts with nobody registered (deleting users cascades to their plans, requests, chats and blocks)."""
    with db.tx() as c:
        c.execute("DELETE FROM users")
        c.execute("DELETE FROM reports")


PORTO = (41.1579, -8.6291)
PNG = "data:image/png;base64," + "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
_n = itertools.count(1)
YEAR = date.today().year - 30


def signup(client, name="Ana", email=None, year=YEAR, agreed=True, password="correct-horse-battery"):
    email = email or f"person{next(_n)}@example.com"
    r = client.post("/api/people/register", json={"email": email, "password": password, "display_name": name, "birth_year": year, "agreed": agreed})
    return r, email


def person(client, name="Ana", interests=("live-music", "coffee"), visible=True):
    r, email = signup(client, name)
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    uid = r.json()["me"]["id"]
    client.patch("/api/people/me", json={"interests": list(interests), "languages": ["English"], "bio": f"Hi, I am {name}.", "visible": visible}, headers=h)
    return h, uid, email


def looking(client, h, text, radius=3000, at=PORTO):
    return client.post("/api/people/looking", json={"text": text, "lat": at[0], "lng": at[1], "radius_m": radius}, headers=h)


def ids(items):
    return {p["id"] for p in items}


# ---------------------------------------------------------------- accounts and safety gates

def test_only_adults_who_accept_the_rules_can_register(client):
    assert signup(client, year=date.today().year - 17)[0].status_code == 403
    assert signup(client, year=date.today().year - 18)[0].status_code == 200
    assert signup(client, agreed=False)[0].status_code == 400
    assert signup(client, password="short")[0].status_code == 400
    r, email = signup(client)
    assert signup(client, email=email)[0].status_code == 409


def test_sign_in_and_out_and_auth_is_required(client):
    r, email = signup(client, "Bea")
    token = r.json()["token"]
    assert client.get("/api/people/me").status_code == 401
    assert client.get("/api/people/me", headers={"Authorization": f"Bearer {token}"}).json()["me"]["display_name"] == "Bea"
    assert client.post("/api/people/login", json={"email": email, "password": "wrong-password-1"}).status_code == 401
    ok = client.post("/api/people/login", json={"email": email, "password": "correct-horse-battery"})
    assert ok.status_code == 200
    client.post("/api/people/logout", headers={"Authorization": f"Bearer {token}"})
    assert client.get("/api/people/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_a_partner_session_is_not_a_people_session(client):
    from tests.test_partners import signup as partner_signup
    headers, _ = partner_signup(client)
    assert client.get("/api/people/me", headers=headers).status_code == 401


def test_profile_only_keeps_known_interests_and_never_exposes_private_fields_to_others(client):
    h, uid, email = person(client, "Cai", interests=["hiking", "made-up-thing"])
    other, _, _ = person(client, "Dee")
    assert client.get("/api/people/me", headers=h).json()["me"]["interests"] == ["hiking"]
    client.post("/api/people/attend", json={"place_key": "osm-node-1", "place_name": "Bar Um", "dest": "OPO", "lat": 41.15, "lng": -8.61}, headers=h)
    seen = client.get("/api/people/attendees", params={"place_key": "osm-node-1"}, headers=other).json()["people"][0]
    assert set(seen) == {"id", "display_name", "bio", "interests", "languages", "home_city", "photo_url", "shared", "demo"}
    assert email not in json.dumps(seen) and "birth" not in json.dumps(seen)


# ---------------------------------------------------------------- photos

def test_a_photo_waits_for_approval_and_is_hidden_from_others_until_then(client):
    h, uid, _ = person(client, "Eli")
    other, _, _ = person(client, "Flo")
    assert client.post("/api/people/me/photo", json={"image": PNG}, headers=h).json()["status"] == "pending"
    assert client.get("/api/people/me", headers=h).json()["me"]["photo_url"]  # the owner can see it
    client.post("/api/people/attend", json={"place_key": "osm-node-2", "place_name": "Bar Dois", "dest": "OPO", "lat": 41.15, "lng": -8.61}, headers=h)
    shown = lambda: client.get("/api/people/attendees", params={"place_key": "osm-node-2"}, headers=other).json()["people"][0]["photo_url"]
    assert shown() is None
    pending = client.get("/api/admin/people/photos", headers=ADMIN).json()["photos"]
    assert [p["user_id"] for p in pending] == [uid]
    assert client.post(f"/api/admin/people/photos/{uid}/approve", headers=ADMIN).status_code == 200
    url = shown()
    assert url and client.get(url).status_code == 200 and client.get(url).headers["content-type"] == "image/png"


def test_a_rejected_photo_is_deleted(client):
    h, uid, _ = person(client, "Gus")
    client.post("/api/people/me/photo", json={"image": PNG}, headers=h)
    name = client.get("/api/people/me", headers=h).json()["me"]["photo_url"].rsplit("/", 1)[1]
    assert (users.photo_dir() / name).exists()
    client.post(f"/api/admin/people/photos/{uid}/reject", headers=ADMIN)
    assert not (users.photo_dir() / name).exists()
    assert client.get("/api/people/me", headers=h).json()["me"]["photo_status"] == "rejected"


@pytest.mark.parametrize("image", [
    "not a data url", "data:image/gif;base64,R0lGODlhAQABAAAAACw=", "data:image/png;base64," + base64.b64encode(b"this is not a png").decode(),
    "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 500_000).decode(),
], ids=["not-a-data-url", "gif", "not-really-a-png", "too-big"])
def test_bad_photos_are_refused(client, image):
    h, _, _ = person(client, "Hal")
    assert client.post("/api/people/me/photo", json={"image": image}, headers=h).status_code in (422, 400)


def test_photo_urls_cannot_be_guessed_or_used_for_path_tricks(client):
    assert client.get("/api/people/photo/../../etc/passwd").status_code in (404, 400)
    assert client.get("/api/people/photo/" + "0" * 32 + ".png").status_code == 404
    assert client.get("/api/people/photo/anything.png").status_code == 404


# ---------------------------------------------------------------- places

def attend(client, h, key="osm-node-9", name="Club Nove", day=None, lat=41.15, lng=-8.61, dest="OPO"):
    body = {"place_key": key, "place_name": name, "dest": dest, "lat": lat, "lng": lng}
    if day:
        body["day"] = day.isoformat()
    return client.post("/api/people/attend", json=body, headers=h)


def test_registering_to_a_place_shows_you_to_others_going_and_counts_are_public(client):
    a, a_id, _ = person(client, "Ivy")
    b, b_id, _ = person(client, "Jo")
    attend(client, a, "osm-node-30")
    attend(client, b, "osm-node-30")
    assert client.get("/api/people/counts", params={"keys": "osm-node-30,osm-node-31"}).json()["counts"] == {"osm-node-30": 2}
    seen = client.get("/api/people/attendees", params={"place_key": "osm-node-30"}, headers=a).json()
    assert seen["going"] is True and ids(seen["people"]) == {b_id}  # never yourself
    assert client.get("/api/people/attendees", params={"place_key": "osm-node-30"}).status_code == 401


def test_hidden_profiles_are_not_counted_or_listed(client):
    a, _, _ = person(client, "Kit")
    ghost, _, _ = person(client, "Lou", visible=False)
    attend(client, a, "osm-node-40")
    attend(client, ghost, "osm-node-40")
    assert client.get("/api/people/counts", params={"keys": "osm-node-40"}).json()["counts"] == {"osm-node-40": 1}
    assert client.get("/api/people/attendees", params={"place_key": "osm-node-40"}, headers=a).json()["people"] == []


def test_place_registration_validation(client):
    h, _, _ = person(client, "Max")
    assert attend(client, h, lat=48.85, lng=2.35).status_code == 422            # Paris coordinates for a Porto place
    assert attend(client, h, dest="Atlantis").status_code == 422
    assert attend(client, h, key="BAD KEY!").status_code == 422
    assert attend(client, h, day=date.today() - timedelta(days=1)).status_code == 422
    assert attend(client, h, day=date.today() + timedelta(days=15)).status_code == 422
    ok = attend(client, h, key="osm-node-50")
    assert ok.status_code == 200 and attend(client, h, key="osm-node-50").json()["id"] == ok.json()["id"]  # registering twice is one entry
    assert client.get("/api/people/me", headers=h).json()["plans"][0]["place_name"] == "Club Nove"
    assert client.delete(f"/api/people/attend/{ok.json()['id']}", headers=h).status_code == 200


def test_at_most_ten_places_a_day(client):
    h, _, _ = person(client, "Ned")
    codes = [attend(client, h, key=f"osm-node-{100 + i}").status_code for i in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429


# ---------------------------------------------------------------- reading a request

def test_keyword_reader_finds_activity_day_and_part(client):
    p = intents._fallback("Coffee and live music tomorrow evening, ideally someone who speaks Spanish and is relaxed", date(2026, 9, 21))
    assert set(p["tags"]) >= {"coffee", "live-music"} and p["day"] == date(2026, 9, 22) and p["part"] == "evening"
    assert p["languages"] == ["Spanish"] and p["vibes"] == ["relaxed"]


def test_requests_for_protected_traits_are_ignored_and_the_person_is_told(client):
    h, _, _ = person(client, "Ora")
    r = looking(client, h, "Looking for women aged 25-30 to go hiking")
    assert r.status_code == 200
    assert any("do not filter people by gender, age" in n for n in r.json()["notes"])
    assert r.json()["request"]["tags"] == ["hiking"]
    assert "women" not in r.json()["request"]["summary"].lower()


def test_ordinary_words_do_not_trigger_the_protected_traits_note(client):
    assert not vocab.mentions_sensitive_filter("explore the old town, then black coffee and a single malt tasting")


def test_a_request_with_no_activity_is_refused_with_help(client):
    h, _, _ = person(client, "Pat")
    r = looking(client, h, "just hanging around somehow")
    assert r.status_code == 422 and "activity" in r.json()["detail"]


# ---------------------------------------------------------------- matching

def test_people_who_want_the_same_thing_nearby_match_each_other_without_leaking_location(client):
    a, a_id, _ = person(client, "Quin", interests=["live-music"])
    b, b_id, _ = person(client, "Rae", interests=["live-music"])
    looking(client, a, "Live music tonight, someone relaxed who speaks English", at=(41.1579, -8.6291))
    res = looking(client, b, "Anyone for live music tonight?", at=(41.1601, -8.6250)).json()
    assert ids(res["people"]) == {a_id}
    card = res["people"][0]
    assert card["shared"] == ["live-music"] and card["distance"] == "within 1 km" and card["why"][0].startswith("You both want live music")
    text = json.dumps(res["people"])
    assert "41.15" not in text and "-8.62" not in text and "lat" not in card and "email" not in text


@pytest.mark.parametrize("other_text,other_at,other_visible", [
    ("Hiking tonight", PORTO, True),                              # different activity
    ("Live music tomorrow", PORTO, True),                         # different day
    ("Live music tonight", (41.55, -8.42), True),                 # a different city
    ("Live music tonight", PORTO, False),                         # profile hidden
])
def test_people_who_do_not_fit_are_not_matched(client, other_text, other_at, other_visible):
    a, _, _ = person(client, "Sam", interests=["live-music"])
    b, _, _ = person(client, "Tia", interests=["hiking"], visible=other_visible)
    looking(client, b, other_text, at=other_at)
    assert looking(client, a, "Live music tonight").json()["people"] == []


def test_blocked_people_never_match_in_either_direction(client):
    a, a_id, _ = person(client, "Uma")
    b, b_id, _ = person(client, "Vic")
    looking(client, b, "Coffee tonight")
    assert ids(looking(client, a, "Coffee tonight").json()["people"]) == {b_id}
    client.post("/api/people/block", json={"user_id": b_id}, headers=a)
    assert looking(client, a, "Coffee tonight").json()["people"] == []
    assert looking(client, b, "Coffee tonight").json()["people"] == []


def test_people_going_to_places_nearby_are_offered_too(client):
    a, _, _ = person(client, "Wes", interests=["live-music"])
    b, b_id, _ = person(client, "Xia", interests=["live-music", "coffee"])
    attend(client, b, "osm-node-77", "Sala Sete", lat=41.1580, lng=-8.6290)
    res = looking(client, a, "Live music tonight").json()
    place = res["at_places"][0]
    assert place["place_name"] == "Sala Sete" and place["count"] == 1 and place["people"][0]["id"] == b_id and place["people"][0]["shared"] == ["live-music"]


def test_only_three_open_requests_at_a_time(client):
    h, _, _ = person(client, "Yan")
    for i in range(5):
        looking(client, h, f"Coffee number {i}")
    assert len(client.get("/api/people/me", headers=h).json()["requests"]) == 3
    rid = client.get("/api/people/me", headers=h).json()["requests"][0]["id"]
    assert client.delete(f"/api/people/looking/{rid}", headers=h).status_code == 200


# ---------------------------------------------------------------- consent, chat and safety

def two_people(client):
    a, a_id, _ = person(client, "Zed")
    b, b_id, _ = person(client, "Amy")
    return a, a_id, b, b_id


def test_nobody_can_chat_until_the_other_person_accepts(client):
    a, a_id, b, b_id = two_people(client)
    r = client.post("/api/people/connect", json={"to_user": b_id, "message": "Hi, live music tonight?"}, headers=a).json()
    cid = r["id"]
    assert r["status"] == "pending"
    assert client.post(f"/api/people/chats/{cid}/messages", json={"body": "hello"}, headers=a).status_code == 404
    assert client.get(f"/api/people/chats/{cid}/messages", headers=b).status_code == 404
    inbox = client.get("/api/people/connections", headers=b).json()
    assert inbox["incoming"][0]["message"] == "Hi, live music tonight?" and inbox["incoming"][0]["person"]["id"] == a_id
    assert client.post(f"/api/people/connections/{cid}/respond", json={"accept": True}, headers=a).status_code == 404  # only the receiver decides
    assert client.post(f"/api/people/connections/{cid}/respond", json={"accept": True}, headers=b).status_code == 200
    assert client.post(f"/api/people/chats/{cid}/messages", json={"body": "hello Amy"}, headers=a).status_code == 200
    assert client.post(f"/api/people/chats/{cid}/messages", json={"body": "hi Zed!"}, headers=b).status_code == 200
    msgs = client.get(f"/api/people/chats/{cid}/messages", headers=a).json()["messages"]
    assert [(m["body"], m["mine"]) for m in msgs] == [("hello Amy", True), ("hi Zed!", False)]
    assert client.get(f"/api/people/chats/{cid}/messages", params={"after": msgs[0]["id"]}, headers=a).json()["messages"][0]["body"] == "hi Zed!"
    chats = client.get("/api/people/connections", headers=a).json()["chats"]
    assert chats[0]["last"]["body"] == "hi Zed!" and chats[0]["last"]["mine"] is False


def test_a_stranger_cannot_read_or_write_someone_elses_chat(client):
    a, _, b, b_id = two_people(client)
    cid = client.post("/api/people/connect", json={"to_user": b_id}, headers=a).json()["id"]
    client.post(f"/api/people/connections/{cid}/respond", json={"accept": True}, headers=b)
    c, _, _ = person(client, "Ben")
    assert client.get(f"/api/people/chats/{cid}/messages", headers=c).status_code == 404
    assert client.post(f"/api/people/chats/{cid}/messages", json={"body": "hi"}, headers=c).status_code == 404


def test_asking_someone_who_already_asked_you_connects_you(client):
    a, a_id, b, b_id = two_people(client)
    client.post("/api/people/connect", json={"to_user": b_id}, headers=a)
    assert client.post("/api/people/connect", json={"to_user": a_id}, headers=b).json()["status"] == "accepted"
    assert client.post("/api/people/connect", json={"to_user": a_id}, headers=b).status_code == 409


def test_a_declined_request_cannot_be_repeated_and_you_cannot_connect_to_yourself_or_hidden_people(client):
    a, a_id, b, b_id = two_people(client)
    cid = client.post("/api/people/connect", json={"to_user": b_id}, headers=a).json()["id"]
    client.post(f"/api/people/connections/{cid}/respond", json={"accept": False}, headers=b)
    assert client.post("/api/people/connect", json={"to_user": b_id}, headers=a).status_code == 409
    assert client.post("/api/people/connect", json={"to_user": a_id}, headers=a).status_code == 400
    ghost, ghost_id, _ = person(client, "Cy", visible=False)
    assert client.post("/api/people/connect", json={"to_user": ghost_id}, headers=a).status_code == 404


def test_blocking_closes_the_chat_and_hides_both_people(client):
    a, a_id, b, b_id = two_people(client)
    cid = client.post("/api/people/connect", json={"to_user": b_id}, headers=a).json()["id"]
    client.post(f"/api/people/connections/{cid}/respond", json={"accept": True}, headers=b)
    client.post(f"/api/people/chats/{cid}/messages", json={"body": "hi"}, headers=a)
    assert client.post("/api/people/block", json={"user_id": a_id}, headers=b).status_code == 200
    assert client.get(f"/api/people/chats/{cid}/messages", headers=a).status_code == 404
    assert client.post(f"/api/people/chats/{cid}/messages", json={"body": "still there?"}, headers=a).status_code == 404
    assert client.get("/api/people/connections", headers=a).json()["chats"] == []
    assert client.get("/api/people/connections", headers=b).json()["chats"] == []
    assert client.post("/api/people/connect", json={"to_user": a_id}, headers=b).status_code == 404
    assert client.get("/api/people/me", headers=b).json()["blocked"] == [{"id": a_id, "display_name": "Zed"}]
    client.post("/api/people/unblock", json={"user_id": a_id}, headers=b)
    assert client.get("/api/people/me", headers=b).json()["blocked"] == []


def test_messages_are_limited_in_length_and_must_not_be_empty(client):
    a, _, b, b_id = two_people(client)
    cid = client.post("/api/people/connect", json={"to_user": b_id}, headers=a).json()["id"]
    client.post(f"/api/people/connections/{cid}/respond", json={"accept": True}, headers=b)
    assert client.post(f"/api/people/chats/{cid}/messages", json={"body": "   "}, headers=a).status_code == 422
    assert client.post(f"/api/people/chats/{cid}/messages", json={"body": "x" * 501}, headers=a).status_code == 422


def test_reports_reach_the_moderator_and_a_ban_ends_the_account(client):
    a, a_id, b, b_id = two_people(client)
    assert client.post("/api/people/report", json={"user_id": b_id, "reason": "not a reason"}, headers=a).status_code == 422
    assert client.post("/api/people/report", json={"user_id": b_id, "reason": "harassment", "detail": "rude"}, headers=a).status_code == 200
    reports = client.get("/api/admin/people/reports", headers=ADMIN).json()["reports"]
    mine = next(r for r in reports if r["target_id"] == b_id)
    assert mine["reason"] == "harassment" and mine["open_against"] == 1
    assert client.get("/api/admin/people/reports").status_code == 401
    assert client.post(f"/api/admin/people/reports/{mine['id']}/resolve", json={"ban": True}, headers=ADMIN).status_code == 200
    assert client.get("/api/people/me", headers=b).status_code == 401          # signed out at once
    email = users.get_row(b_id)["email"]
    assert client.post("/api/people/login", json={"email": email, "password": "correct-horse-battery"}).status_code == 403


def test_deleting_an_account_removes_everything(client):
    a, a_id, b, b_id = two_people(client)
    email = users.get_row(a_id)["email"]
    client.post("/api/people/me/photo", json={"image": PNG}, headers=a)
    name = client.get("/api/people/me", headers=a).json()["me"]["photo_url"].rsplit("/", 1)[1]
    attend(client, a, "osm-node-88")
    cid = client.post("/api/people/connect", json={"to_user": b_id}, headers=a).json()["id"]
    client.post(f"/api/people/connections/{cid}/respond", json={"accept": True}, headers=b)
    client.post(f"/api/people/chats/{cid}/messages", json={"body": "bye"}, headers=a)
    assert client.post("/api/people/me/delete", json={"password": "wrong-password-1"}, headers=a).status_code == 401
    assert client.post("/api/people/me/delete", json={"password": "correct-horse-battery"}, headers=a).status_code == 200
    assert users.get_row(a_id) is None and not (users.photo_dir() / name).exists()
    with db.tx() as c:
        left = [c.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} = ?", (a_id,)).fetchone()[0]
                for t, col in (("attendances", "user_id"), ("messages", "sender_id"), ("connections", "from_user"), ("intents", "user_id"))]
    assert left == [0, 0, 0, 0]
    assert client.get("/api/people/me", headers=a).status_code == 401
    assert client.post("/api/people/login", json={"email": email, "password": "correct-horse-battery"}).status_code == 401


def test_people_options_list_the_rules_and_the_vocabulary(client):
    body = client.get("/api/people/options").json()
    assert body["min_age"] == 18 and len(body["rules"]) >= 5 and "harassment" in body["report_reasons"]
    assert {"key": "live-music", "label": "Live music"} in body["activities"]
