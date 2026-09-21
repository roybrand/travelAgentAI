"""Real monthly climate from Open-Meteo's free historical archive (no API key), turned into a 1-5
"how good is this month to visit" score. Results are cached on disk for a year."""
from collections import defaultdict

from app.live.http import DAY, cached, get_json

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
YEARS = (2019, 2023)  # five full years smooths out unusual weather


def suitability(tmax: float, rainy_fraction: float) -> int:
    """Blend comfort (daytime highs of 21-28C are ideal) with how often it rains, into 1-5.

    This is a transparent heuristic over real measurements, not a measurement itself."""
    if tmax < 21:
        comfort = max(0.0, 1 - (21 - tmax) / 17)  # 4C or colder scores zero
    elif tmax > 28:
        comfort = max(0.0, 1 - (tmax - 28) / 12)  # 40C or hotter scores zero
    else:
        comfort = 1.0
    dryness = 1 - min(1.0, rainy_fraction * 1.3)
    return max(1, min(5, round(1 + 4 * (0.7 * comfort + 0.3 * dryness))))


def _aggregate(daily: dict) -> dict:
    """Daily series -> per-month averages and scores."""
    buckets = defaultdict(lambda: {"tmax": [], "tmin": [], "rain": [], "rainy": 0, "days": 0})
    for day, hi, lo, rain in zip(daily["time"], daily["temperature_2m_max"], daily["temperature_2m_min"], daily["precipitation_sum"]):
        if hi is None or lo is None:
            continue
        b = buckets[int(day[5:7])]
        b["tmax"].append(hi)
        b["tmin"].append(lo)
        b["rain"].append(rain or 0.0)
        b["rainy"] += 1 if (rain or 0) >= 1.0 else 0
        b["days"] += 1

    months, scores = [], []
    for m in range(1, 13):
        b = buckets[m]
        n = max(1, b["days"])
        tmax = sum(b["tmax"]) / n
        rainy_fraction = b["rainy"] / n
        years = YEARS[1] - YEARS[0] + 1
        months.append({
            "tmax": round(tmax, 1),
            "tmin": round(sum(b["tmin"]) / n, 1),
            "rain_mm": round(sum(b["rain"]) / years),  # average monthly total
            "rainy_days": round(rainy_fraction * 30),
        })
        scores.append(suitability(tmax, rainy_fraction))
    return {"months": months, "scores": scores}


def monthly_climate(dest: dict) -> dict:
    def fetch():
        data = get_json(ARCHIVE, {
            "latitude": dest["lat"], "longitude": dest["lng"],
            "start_date": f"{YEARS[0]}-01-01", "end_date": f"{YEARS[1]}-12-31",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum", "timezone": "UTC",
        }, timeout=60)
        return _aggregate(data["daily"])

    result = cached(f"climate_{dest['code']}", 365 * DAY, fetch)
    return {**result, "source": "Open-Meteo historical weather 2019-2023"}


def season_note(clim: dict, names: list[str]) -> str:
    """Plain-language summary written from the real numbers (no AI involved)."""
    months = clim["months"]
    scores = clim["scores"]
    warmest = max(range(12), key=lambda i: months[i]["tmax"])
    coolest = min(range(12), key=lambda i: months[i]["tmax"])
    wettest = max(range(12), key=lambda i: months[i]["rain_mm"])
    top = max(scores)
    best = [names[i] for i, s in enumerate(scores) if s == top]
    return (
        f"Typical daytime highs range from {months[coolest]['tmax']:.0f}°C in {names[coolest]} to "
        f"{months[warmest]['tmax']:.0f}°C in {names[warmest]}. Wettest month: {names[wettest]} "
        f"(about {months[wettest]['rain_mm']} mm). Most comfortable: {', '.join(best)}. "
        f"Based on {clim['source']}."
    )
