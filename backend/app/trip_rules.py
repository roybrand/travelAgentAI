"""Top-level deterministic itinerary business rules."""
from __future__ import annotations

from datetime import date

from . import deal_rules, stay_rules

SOURCE_QUALITY = {
    "amadeus": "live",
    "live": "live",
    "travelpayouts": "recent",
    "estimate": "estimate",
    "demo": "demo",
    "showcase": "demo",
    "none": "missing",
}


def _parse_day(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _source_quality(mode: str | None) -> str:
    return SOURCE_QUALITY.get(mode or "none", "unknown")


def validate_itinerary(itinerary: dict, req: dict, nights: int) -> dict:
    violations: list[str] = []
    warnings: list[str] = []

    start = _parse_day(req.get("start_date"))
    end = _parse_day(req.get("end_date"))
    if not start or not end:
        violations.append("trip_dates_missing_or_invalid")
    elif (end - start).days != nights:
        violations.append("trip_nights_must_match_dates")

    route = itinerary.get("destinations") or []
    if not route:
        violations.append("route_must_have_destination")
    elif len(route) > max(1, nights):
        violations.append("too_many_route_stops_for_trip_length")

    flight = itinerary.get("flight") or {}
    if not flight:
        violations.append("missing_flight")
    elif itinerary.get("destinations") and flight.get("destination") != route[0]:
        violations.append("flight_must_arrive_at_first_route_stop")

    budget = req.get("budget")
    total = itinerary.get("total_cost")
    if budget and total and total > budget:
        warnings.append("trip_exceeds_budget")
    if total and itinerary.get("stay_total_cost") and flight.get("total_price"):
        expected = round(float(itinerary["stay_total_cost"]) + float(flight["total_price"]), 2)
        if round(float(total), 2) != expected:
            violations.append("total_cost_must_equal_flight_plus_stay")

    route_rules = itinerary.get("planning_rules") or {}
    if route_rules.get("valid") is False:
        violations.append("route_days_invalid")

    source_quality = {
        item.get("key", "unknown"): _source_quality(item.get("mode"))
        for item in itinerary.get("data_sources") or []
    }
    for key, quality in source_quality.items():
        if quality in {"demo", "estimate", "recent", "missing", "unknown"}:
            warnings.append(f"{key}_source_quality:{quality}")

    stay = stay_rules.validate_stays(itinerary, req, nights)
    deals = deal_rules.validate_deals(itinerary, req)
    violations.extend(f"stay:{v}" for v in stay["violations"])
    violations.extend(f"deal:{v}" for v in deals["violations"])
    warnings.extend(f"stay:{w}" for w in stay["warnings"])
    warnings.extend(f"deal:{w}" for w in deals["warnings"])

    return {
        "valid": not violations,
        "violations": sorted(set(violations)),
        "warnings": sorted(set(warnings)),
        "source_quality": source_quality,
        "checks": {
            "trip": True,
            "stays": stay,
            "deals": deals,
            "route_days": route_rules,
        },
    }
