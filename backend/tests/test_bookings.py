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
