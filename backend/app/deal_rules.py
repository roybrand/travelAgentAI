"""Deterministic partner-deal placement and source-quality rules."""
from __future__ import annotations

from datetime import date


def _parse_day(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def validate_deals(itinerary: dict, req: dict) -> dict:
    violations: list[str] = []
    warnings: list[str] = []
    start = _parse_day(req.get("start_date"))
    end = _parse_day(req.get("end_date"))
    route = set(itinerary.get("destinations") or [itinerary.get("destination")])

    for deal in itinerary.get("partner_deals") or []:
        deal_id = deal.get("id")
        if deal.get("dest") not in route:
            violations.append(f"deal_outside_trip_route:{deal_id}")
        valid_from = _parse_day(deal.get("valid_from"))
        valid_to = _parse_day(deal.get("valid_to"))
        if start and valid_to and valid_to < start:
            violations.append(f"deal_expired_before_trip:{deal_id}")
        if end and valid_from and valid_from > end:
            violations.append(f"deal_starts_after_trip:{deal_id}")
        if deal.get("category") != "flight" and (deal.get("lat") is None or deal.get("lng") is None):
            violations.append(f"place_deal_missing_location:{deal_id}")
        if not deal.get("match") and not deal.get("why"):
            warnings.append(f"deal_missing_match_reason:{deal_id}")
        if deal.get("discount_pct", 0) <= 0 and deal.get("reference_price") is None:
            warnings.append(f"deal_without_discount_claim:{deal_id}")

    return {"valid": not violations, "violations": sorted(set(violations)), "warnings": sorted(set(warnings))}
