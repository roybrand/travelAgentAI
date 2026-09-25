"""Demo bookings: the flow end to end, totals recomputed on the server, nothing personal stored, manage token needed."""
from app.partners import db
from tests.test_partners import ADMIN, fresh_limits  # noqa: F401  (autouse fixture: resets rate limits, temp activity log)


def body(**over):
    b = {
        "origin": "LON", "destination": "LIS", "start_date": "2026-11-10", "end_date": "2026-11-14", "travelers": 2,
        "flight": {"airline": "TAP", "depart_time": "08:30", "stops": 0, "total_price": 300, "price_source": "estimate"},
        "stay": {"name": "Casa Azul", "price_per_night": 100, "price_source": "demo"},
        "activities": [
            {"name": "Tram 28 ride", "day": 1, "part": "morning", "cost": 3},
            {"name": "Miradouro sunset", "day": 2, "part": "evening", "cost": 0},
        ],
        "demo_acknowledged": True,
    }
    b.update(over)
    return b


def test_booking_end_to_end(client):
    assert client.post("/api/bookings/checkout").json() == {"ok": True}
    r = client.post("/api/bookings", json=body())
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["demo"] is True and b["status"] == "confirmed" and b["reference"].startswith("WF-")
    # 300 flight + 4 nights x 100 + 3 x 2 travelers; the free activity adds nothing and gets no ticket
    assert b["totals"] == {"nights": 4, "flight": 300, "stay": 400, "activities": 6, "total": 706}
    assert [t["name"] for t in b["tickets"]] == ["Tram 28 ride"] and b["free_activities"] == ["Miradouro sunset"]
    assert len(b["flight"]["pnr"]) == 6 and b["stay"]["confirmation"].startswith("H")

    view = client.get(f"/api/bookings/{b['reference']}", params={"token": b["manage_token"]}).json()
    assert view["status"] == "confirmed" and view["total"] == 706
    assert client.get(f"/api/bookings/{b['reference']}", params={"token": "wrong-token-123"}).status_code == 404

    assert client.post(f"/api/bookings/{b['reference']}/cancel", json={"token": "wrong-token-123"}).status_code == 404
    done = client.post(f"/api/bookings/{b['reference']}/cancel", json={"token": b["manage_token"]}).json()
    assert done["status"] == "cancelled" and done["cancelled_at"]

    funnel = {s["label"]: s["count"] for s in client.get("/api/admin/analytics/summary", headers=ADMIN).json()["booking_funnel"]}
    assert funnel["Opened checkout"] >= 1 and funnel["Booked (demo)"] >= 1 and funnel["Cancelled"] >= 1


def test_booking_stores_no_personal_details(client):
    client.post("/api/bookings", json=body())
    with db.tx() as c:
        cols = {r["name"] for r in c.execute("PRAGMA table_info(demo_bookings)")}
    assert not cols & {"name", "email", "phone", "lead_name", "lead_email"}
    assert "token_hash" in cols and "manage_token" not in cols


def test_booking_rejects_bad_input(client):
    assert client.post("/api/bookings", json=body(demo_acknowledged=False)).status_code == 422
    assert client.post("/api/bookings", json=body(end_date="2026-11-10")).status_code == 422
    bad_day = body(activities=[{"name": "Too late", "day": 9, "part": "night", "cost": 5}])
    assert client.post("/api/bookings", json=bad_day).status_code == 422
    assert client.post("/api/bookings", json=body(travelers=0)).status_code == 422


# ---------------------------------------------------------------- booking one partner deal

def _a_live_deal(client):
    from datetime import date, timedelta
    from tests.test_partners import approve, deal_body, signup, submit
    headers, _ = signup(client)
    deal_id = submit(client, headers)
    approve(client, deal_id)
    return {"id": deal_id, **deal_body()}, date.today() + timedelta(days=1)


def test_book_a_deal_prices_from_the_database_and_can_be_cancelled_once(client):
    deal, day = _a_live_deal(client)
    r = client.post("/api/bookings/deal", json={"deal_id": deal["id"], "date": day.isoformat(), "quantity": 3, "demo_acknowledged": True, "price": 1})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["demo"] and b["reference"].startswith("WD-") and b["voucher"].startswith("V-")
    assert b["total"] == deal["price"] * 3 and b["deal"]["title"] == deal["title"]
    first = client.post(f"/api/bookings/deal/{b['reference']}/cancel", json={"token": b["manage_token"]}).json()
    again = client.post(f"/api/bookings/deal/{b['reference']}/cancel", json={"token": b["manage_token"]}).json()
    assert first["status"] == again["status"] == "cancelled" and first["cancelled_at"] == again["cancelled_at"]
    assert client.post(f"/api/bookings/deal/{b['reference']}/cancel", json={"token": "not-the-token-123"}).status_code == 404


def test_book_a_deal_only_when_it_is_live_on_that_day(client):
    from datetime import date, timedelta
    deal, _ = _a_live_deal(client)
    too_late = (date.fromisoformat(deal["valid_to"]) + timedelta(days=1)).isoformat()
    assert client.post("/api/bookings/deal", json={"deal_id": deal["id"], "date": too_late, "quantity": 1, "demo_acknowledged": True}).status_code == 409
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    assert client.post("/api/bookings/deal", json={"deal_id": deal["id"], "date": yesterday, "quantity": 1, "demo_acknowledged": True}).status_code == 422
    assert client.post("/api/bookings/deal", json={"deal_id": 999999, "date": date.today().isoformat(), "quantity": 1, "demo_acknowledged": True}).status_code == 409
    assert client.post("/api/bookings/deal", json={"deal_id": deal["id"], "date": date.today().isoformat(), "quantity": 11, "demo_acknowledged": True}).status_code == 422


# ---------------------------------------------------------------- changing the day plan after booking

def test_update_tickets_charges_refunds_and_moves_without_touching_flights_or_stay(client):
    b = client.post("/api/bookings", json=body()).json()  # tickets: Tram 28 (£3 pp, day 1 morning); the free sunset has none
    token, ref = b["manage_token"], b["reference"]
    tram = next(t for t in b["tickets"] if t["name"] == "Tram 28 ride")

    plan = [
        {"name": "Tram 28 ride", "day": 2, "part": "afternoon", "cost": 3},   # moved
        {"name": "Sunset sail", "day": 3, "part": "evening", "cost": 35},     # added, paid
        {"name": "Miradouro sunset", "day": 2, "part": "evening", "cost": 0}, # free: never a ticket
    ]
    r = client.put(f"/api/bookings/{ref}/activities", json={"token": token, "activities": plan}).json()
    assert r["added"] == ["Sunset sail"] and r["moved"] == ["Tram 28 ride"] and r["removed"] == []
    assert r["charged"] == 70 and r["refunded"] == 0                          # 35 x 2 travelers
    assert r["totals"] == {"nights": 4, "flight": 300, "stay": 400, "activities": 76, "total": 776}
    assert next(t for t in r["tickets"] if t["name"] == "Tram 28 ride")["code"] == tram["code"]  # same ticket, new date

    r = client.put(f"/api/bookings/{ref}/activities", json={"token": token, "activities": plan[1:]}).json()
    assert r["removed"] == ["Tram 28 ride"] and r["refunded"] == 6 and r["totals"]["total"] == 770
    assert client.get(f"/api/bookings/{ref}", params={"token": token}).json()["total"] == 770

    assert client.put(f"/api/bookings/{ref}/activities", json={"token": "wrong-token-123", "activities": []}).status_code == 404
    client.post(f"/api/bookings/{ref}/cancel", json={"token": token})
    assert client.put(f"/api/bookings/{ref}/activities", json={"token": token, "activities": []}).status_code == 409


def test_a_deal_booking_says_how_it_is_paid(client):
    deal, day = _a_live_deal(client)
    at_venue = client.post("/api/bookings/deal", json={"deal_id": deal["id"], "date": day.isoformat(), "quantity": 1, "demo_acknowledged": True}).json()
    now = client.post("/api/bookings/deal", json={"deal_id": deal["id"], "date": day.isoformat(), "quantity": 1, "pay": "now", "demo_acknowledged": True}).json()
    assert at_venue["pay"] == "venue" and now["pay"] == "now"
    assert client.post("/api/bookings/deal", json={"deal_id": deal["id"], "date": day.isoformat(), "quantity": 1, "pay": "later", "demo_acknowledged": True}).status_code == 422


def test_older_databases_gain_the_ticket_and_pay_columns(tmp_path, monkeypatch):
    import sqlite3
    from app.partners import db as dbmod
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(
        "CREATE TABLE demo_bookings (id INTEGER PRIMARY KEY, reference TEXT);"
        "CREATE TABLE demo_deal_bookings (id INTEGER PRIMARY KEY, reference TEXT);"
    )
    old.close()
    monkeypatch.setenv("WAYFINDER_DB", str(path))
    with dbmod.tx() as c:
        assert "tickets" in {r["name"] for r in c.execute("PRAGMA table_info(demo_bookings)")}
        assert "pay" in {r["name"] for r in c.execute("PRAGMA table_info(demo_deal_bookings)")}


# ---------------------------------------------------------------- the business side: reservations and check-in

def test_another_business_never_sees_or_checks_in_someone_elses_reservation(client):
    from tests.test_partners import signup
    deal, day = _a_live_deal(client)
    b = client.post("/api/bookings/deal", json={"deal_id": deal["id"], "date": day.isoformat(), "quantity": 2, "part": "evening", "demo_acknowledged": True}).json()
    assert b["voucher"].startswith("V-") and b["part"] == "evening"
    stranger, _ = signup(client)
    assert all(r["reference"] != b["reference"] for r in client.get("/api/partners/reservations", headers=stranger).json()["reservations"])
    assert client.post("/api/partners/reservations/check", json={"code": b["voucher"]}, headers=stranger).status_code == 404
    assert client.post(f"/api/partners/reservations/{b['reference']}/redeem", headers=stranger).status_code == 404


def test_the_owner_checks_in_the_voucher_once(client):
    from datetime import date, timedelta
    from tests.test_partners import approve, deal_body, signup, submit
    headers, _ = signup(client)
    deal_id = submit(client, headers)
    approve(client, deal_id)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    b = client.post("/api/bookings/deal", json={"deal_id": deal_id, "date": tomorrow, "quantity": 2, "part": "evening", "demo_acknowledged": True}).json()

    res = client.get("/api/partners/reservations", headers=headers).json()
    mine = next(r for r in res["reservations"] if r["reference"] == b["reference"])
    assert mine["voucher"] == b["voucher"] and mine["quantity"] == 2 and mine["pay"] == "venue" and mine["part"] == "evening"
    assert "email" not in mine and "name" not in mine and res["counts"]["upcoming"] >= 1

    check = client.post("/api/partners/reservations/check", json={"code": b["voucher"].lower()}, headers=headers).json()
    assert check["can_redeem"] and any("not today" in w for w in check["warnings"])
    used = client.post(f"/api/partners/reservations/{b['reference']}/redeem", headers=headers).json()
    assert used["status"] == "redeemed" and used["redeemed_at"]
    assert client.post(f"/api/partners/reservations/{b['reference']}/redeem", headers=headers).status_code == 409

    status = client.get(f"/api/bookings/deal/{b['reference']}", params={"token": b["manage_token"]}).json()
    assert status["status"] == "redeemed"
    assert client.post(f"/api/bookings/deal/{b['reference']}/cancel", json={"token": b["manage_token"]}).status_code == 409
    assert client.get(f"/api/bookings/deal/{b['reference']}", params={"token": "wrong-token-123"}).status_code == 404
    assert client.get("/api/partners/reservations").status_code == 401


def test_a_cancelled_reservation_cannot_be_checked_in(client):
    from datetime import date
    from tests.test_partners import approve, signup, submit
    headers, _ = signup(client)
    deal_id = submit(client, headers)
    approve(client, deal_id)
    b = client.post("/api/bookings/deal", json={"deal_id": deal_id, "date": date.today().isoformat(), "quantity": 1, "demo_acknowledged": True}).json()
    client.post(f"/api/bookings/deal/{b['reference']}/cancel", json={"token": b["manage_token"]})
    check = client.post("/api/partners/reservations/check", json={"code": b["reference"]}, headers=headers).json()
    assert not check["can_redeem"] and any("cancelled" in w for w in check["warnings"])
    assert client.post(f"/api/partners/reservations/{b['reference']}/redeem", headers=headers).status_code == 409
