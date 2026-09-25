"""Day-by-day weather for a trip, from Open-Meteo's free forecast (no key).

Only days Open-Meteo can actually forecast (today and the next 15) get weather. Further out there is no forecast, and
the answer says so (with the first date it will be ready) instead of guessing; the season chart covers typical weather.
Offline (the test suite) nothing is fetched.
"""
from datetime import date, timedelta

from app import config
from app.live import catalog
from app.live.http import cached, get_json

HORIZON_DAYS = 16  # Open-Meteo forecasts today plus 15 days
WET_RAIN_PCT = 60  # a day counts as wet from this chance of rain, or...
WET_RAIN_MM = 2.0  # ...this much rain over the day

# WMO weather codes, grouped the way a traveler thinks about them.
_CODES = [
    ((0,), "☀️", "Clear"),
    ((1, 2), "🌤️", "Partly cloudy"),
    ((3,), "☁️", "Cloudy"),
    ((45, 48), "🌫️", "Fog"),
    ((51, 53, 55, 56, 57), "🌦️", "Drizzle"),
    ((61, 63, 65, 66, 67, 80, 81, 82), "🌧️", "Rain"),
    ((71, 73, 75, 77, 85, 86), "🌨️", "Snow"),
    ((95, 96, 99), "⛈️", "Thunderstorms"),
]


def describe(code: int | None) -> tuple[str, str]:
    for codes, icon, label in _CODES:
        if code in codes:
            return icon, label
    return "🌡️", "Forecast"


def parse_daily(payload: dict) -> dict[str, dict]:
    """Open-Meteo daily arrays -> {date: {icon, label, tmax, tmin, rain_pct, rain_mm, wet}}. Missing values stay None."""
    daily = payload.get("daily") or {}
    out = {}
    for i, day in enumerate(daily.get("time") or []):
        def at(key):
            values = daily.get(key) or []
            return values[i] if i < len(values) else None
        code, pct, mm = at("weather_code"), at("precipitation_probability_max"), at("precipitation_sum")
        icon, label = describe(code)
        tmax, tmin = at("temperature_2m_max"), at("temperature_2m_min")
        out[day] = {
            "icon": icon, "label": label,
            "tmax": round(tmax) if tmax is not None else None, "tmin": round(tmin) if tmin is not None else None,
            "rain_pct": pct, "rain_mm": mm,
            "wet": bool((pct is not None and pct >= WET_RAIN_PCT) or (mm is not None and mm >= WET_RAIN_MM) or code in (95, 96, 99)),
        }
    return out


def trip_forecast(dest_code: str, start: date, end: date, today: date | None = None) -> dict:
    """The forecast for the days of a trip that fall inside the forecast window."""
    today = today or date.today()
    dest = catalog.resolve(dest_code)
    if not dest:
        return {"available": False, "reason": "unknown_destination", "days": {}}
    last = today + timedelta(days=HORIZON_DAYS - 1)
    lo, hi = max(start, today), min(end, last)
    if lo > hi:
        ready = start - timedelta(days=HORIZON_DAYS - 1)
        return {"available": False, "reason": "past" if end < today else "too_far", "ready_from": ready.isoformat() if end >= today else None, "days": {}}
    if config.offline():
        return {"available": False, "reason": "offline", "days": {}}

    def fetch():
        return parse_daily(get_json("https://api.open-meteo.com/v1/forecast", {
            "latitude": dest["lat"], "longitude": dest["lng"], "timezone": "auto",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum",
            "start_date": lo.isoformat(), "end_date": hi.isoformat(),
        }, timeout=15))

    try:
        days = cached(f"trip_wx_{dest['code']}_{lo}_{hi}", 3 * 3600, fetch)
    except Exception:
        return {"available": False, "reason": "unavailable", "days": {}}
    return {"available": bool(days), "source": "Open-Meteo forecast", "days": days}
