"""Self-hosted analytics: activity.record() mirrors into analytics_events, and the aggregation functions
built on it (daily_series, total_since, funnel) and the admin summary route. No network."""
from datetime import date, timedelta

from app.partners import activity, db
from tests.test_partners import ADMIN, fresh_limits  # noqa: F401


def seed(event: str, day: str, n: int = 1) -> None:
    with db.tx() as c:
        for _ in range(n):
            c.execute("INSERT INTO analytics_events (event, day, created_at) VALUES (?, ?, ?)", (event, day, f"{day}T12:00:00+00:00"))


def clear():
    with db.tx() as c:
        c.execute("DELETE FROM analytics_events")


def test_record_writes_a_row_into_analytics_events(tmp_path, monkeypatch):
    monkeypatch.setattr(activity, "LOG_PATH", tmp_path / "log.md")
    clear()
    activity.record("user.registered")
    today = date.today().isoformat()
    with db.tx() as c:
        rows = c.execute("SELECT event, day FROM analytics_events WHERE day = ?", (today,)).fetchall()
    assert any(r["event"] == "user.registered" for r in rows)


def test_daily_series_is_zero_filled_and_windowed():
    clear()
    today = date.today()
    seed("message.sent", today.isoformat(), n=3)
    seed("message.sent", (today - timedelta(days=2)).isoformat(), n=1)
    seed("message.sent", (today - timedelta(days=10)).isoformat(), n=99)  # outside a 5-day window
    series = activity.daily_series(["message.sent"], days=5)
    assert len(series) == 5 and series[-1] == {"day": today.isoformat(), "count": 3}
    assert series[-3] == {"day": (today - timedelta(days=2)).isoformat(), "count": 1}
    assert sum(d["count"] for d in series) == 4  # the 10-day-old batch is excluded
    assert series[0]["day"] == (today - timedelta(days=4)).isoformat()  # zero-filled, oldest day first


def test_total_since_sums_multiple_events_within_the_window():
    clear()
    today = date.today().isoformat()
    old = (date.today() - timedelta(days=40)).isoformat()
    seed("connection.requested", today, n=2)
    seed("connection.accepted", today, n=1)
    seed("connection.accepted", old, n=5)
    assert activity.total_since(["connection.requested", "connection.accepted"], days=30) == 3


def test_funnel_returns_a_count_per_step():
    clear()
    today = date.today().isoformat()
    seed("user.registered", today, n=10)
    seed("intent.created", today, n=4)
    steps = activity.funnel([("Registered", ["user.registered"]), ("Posted a request", ["intent.created"])], days=30)
    assert steps == [{"label": "Registered", "count": 10}, {"label": "Posted a request", "count": 4}]


def test_admin_analytics_route_needs_the_admin_token_and_shapes_the_summary(client, tmp_path, monkeypatch):
    monkeypatch.setattr(activity, "LOG_PATH", tmp_path / "log.md")
    clear()
    assert client.get("/api/admin/analytics/summary").status_code == 401
    r = client.get("/api/admin/analytics/summary", headers=ADMIN)
    assert r.status_code == 200
    body = r.json()
    assert body["days"] == 30
    assert set(body["kpis"]) == {"people_registered", "partners_registered", "deals_submitted", "connections_requested", "messages_sent", "reports_filed"}
    assert len(body["daily"]["people_registered"]) == 30
    assert [s["label"] for s in body["people_funnel"]] == ["Registered", "Posted a looking-for request", "Sent a connection request", "Had a request accepted", "Sent a message"]
    assert [s["label"] for s in body["partner_funnel"]] == ["Registered", "Submitted a deal", "Deal approved", "Paid to feature a deal"]


def test_admin_analytics_days_parameter_is_clamped(client, tmp_path, monkeypatch):
    monkeypatch.setattr(activity, "LOG_PATH", tmp_path / "log.md")
    assert client.get("/api/admin/analytics/summary?days=1", headers=ADMIN).json()["days"] == 7
    assert client.get("/api/admin/analytics/summary?days=9999", headers=ADMIN).json()["days"] == 90
