"""Deterministic stay-segment business rules."""
from __future__ import annotations

from datetime import date, timedelta


def _parse_day(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def validate_stays(itinerary: dict, req: dict, nights: int) -> dict:
    violations: list[str] = []
    warnings: list[str] = []
    segments = itinerary.get("stay_segments") or []
    start = _parse_day(req.get("start_date"))

    if nights < 1:
        violations.append("trip_must_have_at_least_one_night")
    if not segments:
        violations.append("missing_stay_segments")
        return {"valid": not violations, "violations": violations, "warnings": warnings}

    covered = 0
    previous_end_day = 0
    for segment in segments:
        start_day = int(segment.get("start_day") or 0)
        end_day = int(segment.get("end_day") or 0)
        seg_nights = int(segment.get("nights") or 0)
        hotel = segment.get("hotel") or {}
        check_in = _parse_day(segment.get("check_in"))
        check_out = _parse_day(segment.get("check_out"))

        if start_day != previous_end_day + 1:
            violations.append("stay_segments_must_be_contiguous")
        if end_day < start_day:
            violations.append("stay_segment_end_before_start")
        if seg_nights != end_day - start_day + 1:
            violations.append("stay_segment_nights_mismatch")
        if start and check_in != start + timedelta(days=start_day - 1):
            violations.append("stay_segment_check_in_mismatch")
        if check_in and check_out and (check_out - check_in).days != seg_nights:
            violations.append("stay_segment_check_out_mismatch")
        if not hotel.get("id") or not hotel.get("name"):
            violations.append("stay_segment_missing_hotel")
        if hotel.get("price_source") in (None, "demo", "estimate"):
            warnings.append(f"stay_price_not_live:{segment.get('destination')}")

        covered += max(0, seg_nights)
        previous_end_day = end_day

    if covered != nights:
        violations.append("stay_segments_must_cover_trip_nights")
    if previous_end_day != nights:
        violations.append("stay_segments_must_end_on_final_night")

    return {"valid": not violations, "violations": sorted(set(violations)), "warnings": sorted(set(warnings))}
