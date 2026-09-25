"""Trips kept with the account: two devices stay in step, the newest edit wins, deletions travel, names never do."""
from app.partners import db
from tests.test_partners import fresh_limits  # noqa: F401  (autouse fixture: resets rate limits, temp activity log)
from tests.test_people import signup


def _token(client, name="Dana"):
    r, _ = signup(client, name)
    return {"Authorization": f"Bearer {r.json()['token']}"}


def trip(tid, when, **extra):
    return {"kind": "trip", "id": tid, "updated_at": when, "data": {"id": tid, "name": "Lisbon", "updatedAt": when, **extra}}


def test_two_devices_stay_in_step(client):
    h = _token(client)
    phone = client.post("/api/account/sync", json={"since": 0, "docs": [trip("t1", "2026-09-25T10:00:00.000Z")]}, headers=h).json()
    assert phone["docs"] == [] and phone["seq"] == 1          # its own upload isn't echoed back

    laptop = client.post("/api/account/sync", json={"since": 0, "docs": []}, headers=h).json()
    assert [d["id"] for d in laptop["docs"]] == ["t1"] and laptop["docs"][0]["data"]["name"] == "Lisbon"

    client.post("/api/account/sync", json={"since": laptop["seq"], "docs": [trip("t1", "2026-09-25T11:00:00.000Z", name="Honeymoon")]}, headers=h)
    again = client.post("/api/account/sync", json={"since": phone["seq"], "docs": []}, headers=h).json()
    assert again["docs"][0]["data"]["name"] == "Honeymoon"


def test_the_newest_edit_wins_and_an_older_one_is_ignored(client):
    h = _token(client)
    client.post("/api/account/sync", json={"docs": [trip("t2", "2026-09-25T12:00:00.000Z", name="New")]}, headers=h)
    stale = client.post("/api/account/sync", json={"since": 0, "docs": [trip("t2", "2026-09-25T09:00:00.000Z", name="Old")]}, headers=h).json()
    assert stale["docs"][0]["data"]["name"] == "New"          # the device gets the newer version back


def test_a_deletion_reaches_the_other_devices(client):
    h = _token(client)
    first = client.post("/api/account/sync", json={"docs": [trip("t3", "2026-09-25T10:00:00.000Z")]}, headers=h).json()
    client.post("/api/account/sync", json={"since": first["seq"], "docs": [{"kind": "trip", "id": "t3", "updated_at": "2026-09-25T10:05:00.000Z", "deleted": True}]}, headers=h)
    other = client.post("/api/account/sync", json={"since": 0}, headers=h).json()
    assert other["docs"] == [{"kind": "trip", "id": "t3", "updated_at": "2026-09-25T10:05:00.000Z", "deleted": True, "data": None}]


def test_names_from_checkout_never_reach_the_server(client):
    h = _token(client)
    booking = {"reference": "WF-ABC234", "lead": {"name": "Dana Levi", "email": "dana@example.com"}, "others": ["Noa Levi"]}
    client.post("/api/account/sync", json={"docs": [trip("t4", "2026-09-25T10:00:00.000Z", booking=booking)]}, headers=h)
    with db.tx() as c:
        stored = c.execute("SELECT data FROM account_docs WHERE doc_id = 't4'").fetchone()[0]
    assert "Dana" not in stored and "dana@example.com" not in stored and "Noa" not in stored and "WF-ABC234" in stored


def test_each_account_sees_only_its_own_and_sign_in_is_required(client):
    a, b = _token(client, "Ana"), _token(client, "Ben")
    client.post("/api/account/sync", json={"docs": [trip("same-id", "2026-09-25T10:00:00.000Z", name="Ana's")]}, headers=a)
    client.post("/api/account/sync", json={"docs": [trip("same-id", "2026-09-25T10:00:00.000Z", name="Ben's")]}, headers=b)
    assert client.post("/api/account/sync", json={"since": 0}, headers=a).json()["docs"][0]["data"]["name"] == "Ana's"
    assert client.post("/api/account/sync", json={"since": 0}).status_code == 401


def test_a_new_device_catches_up_in_pages(client):
    h = _token(client)
    for n in range(0, 60, 20):
        client.post("/api/account/sync", json={"docs": [trip(f"p{i}", "2026-09-25T10:00:00.000Z") for i in range(n, n + 20)]}, headers=h)
    seen, since, calls = set(), 0, 0
    while True:
        r = client.post("/api/account/sync", json={"since": since}, headers=h).json()
        seen |= {d["id"] for d in r["docs"]}
        since, calls = r["seq"], calls + 1
        if not r["more"]:
            break
    assert len(seen) == 60 and calls == 3


def test_bad_documents_are_refused(client):
    h = _token(client)
    assert client.post("/api/account/sync", json={"docs": [{"kind": "trip", "id": "../../etc", "updated_at": "2026-09-25T10:00:00Z", "data": {}}]}, headers=h).status_code == 422
    assert client.post("/api/account/sync", json={"docs": [{"kind": "passport", "id": "x1", "updated_at": "2026-09-25T10:00:00Z", "data": {}}]}, headers=h).status_code == 422
    huge = trip("big", "2026-09-25T10:00:00.000Z", blob="x" * 1_600_000)
    assert client.post("/api/account/sync", json={"docs": [huge]}, headers=h).status_code == 413


def test_deleting_the_account_deletes_its_trips(client):
    r, _ = signup(client, "Gone")
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    client.post("/api/account/sync", json={"docs": [trip("bye", "2026-09-25T10:00:00.000Z")]}, headers=h)
    assert client.post("/api/people/me/delete", headers=h, json={"password": "correct-horse-battery"}).status_code == 200
    with db.tx() as c:
        assert c.execute("SELECT COUNT(*) FROM account_docs WHERE doc_id = 'bye'").fetchone()[0] == 0
