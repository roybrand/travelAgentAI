"""Trip weather: only real forecast days, never a guess, and nothing fetched offline."""
from datetime import date, timedelta

from app.live import forecast

SAMPLE = {"daily": {
    "time": ["2026-10-01", "2026-10-02", "2026-10-03"],
    "weather_code": [0, 63, 95],
    "temperature_2m_max": [24.4, 18.6, 20.0], "temperature_2m_min": [15.2, 13.9, 14.0],
    "precipitation_probability_max": [5, 85, 40], "precipitation_sum": [0.0, 9.1, 1.0],
}}


def test_parse_daily_marks_wet_days_from_chance_amount_or_storms():
    days = forecast.parse_daily(SAMPLE)
    assert days["2026-10-01"] == {"icon": "☀️", "label": "Clear", "tmax": 24, "tmin": 15, "rain_pct": 5, "rain_mm": 0.0, "wet": False}
    assert days["2026-10-02"]["wet"] and days["2026-10-02"]["label"] == "Rain"
    assert days["2026-10-03"]["wet"] and days["2026-10-03"]["label"] == "Thunderstorms"


def test_trips_beyond_the_forecast_window_say_when_it_will_be_ready():
    today = date(2026, 9, 25)
    out = forecast.trip_forecast("LIS", date(2026, 11, 10), date(2026, 11, 15), today=today)
    assert out == {"available": False, "reason": "too_far", "ready_from": "2026-10-26", "days": {}}
    assert forecast.trip_forecast("LIS", date(2026, 9, 1), date(2026, 9, 5), today=today)["reason"] == "past"
    assert forecast.trip_forecast("NOWHERE", today, today, today=today)["reason"] == "unknown_destination"


def test_nothing_is_fetched_offline(client):
    today = date.today()
    r = client.get("/api/trip-weather", params={"dest": "LIS", "start": today.isoformat(), "end": (today + timedelta(days=3)).isoformat()})
    assert r.status_code == 200 and r.json() == {"available": False, "reason": "offline", "days": {}}
    assert client.get("/api/trip-weather", params={"dest": "LIS", "start": "2026-11-15", "end": "2026-11-10"}).status_code == 422
