"""Deterministic route-day planning rules.

Generative planning can suggest places, but route-day shape is a product invariant:
morning starts near the beginning, night ends near the day's end, and every day
continues from the previous one. This module turns guide items into a canonical
route model the UI can render without re-inventing those rules.
"""
from __future__ import annotations

import math

PARTS = ["morning", "afternoon", "evening", "night"]
PART_RULES = {
    "morning": {"target": 0.08, "band": (0.0, 0.28)},
    "afternoon": {"target": 0.36, "band": (0.18, 0.54)},
    "evening": {"target": 0.66, "band": (0.46, 0.82)},
    "night": {"target": 0.94, "band": (0.74, 1.0)},
}


def _has_point(p: dict | None) -> bool:
    return p is not None and p.get("lat") is not None and p.get("lng") is not None


def distance_m(a: dict, b: dict) -> int:
    lat1, lat2 = math.radians(float(a["lat"])), math.radians(float(b["lat"]))
    dlat = lat2 - lat1
    dlng = math.radians(float(b["lng"]) - float(a["lng"]))
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return round(6371000 * 2 * math.asin(math.sqrt(h)))


def _route_lengths(points: list[dict]) -> tuple[list[int], int]:
    lengths = [distance_m(a, b) for a, b in zip(points, points[1:])]
    return lengths, sum(lengths) or 1


def point_at(points: list[dict], progress: float) -> dict | None:
    clean = [p for p in points if _has_point(p)]
    if not clean:
        return None
    if len(clean) == 1:
        return {**clean[0], "progress": 0}
    clamped = max(0.0, min(1.0, float(progress)))
    lengths, total = _route_lengths(clean)
    left = clamped * total
    for idx, length in enumerate(lengths):
        if left <= length or idx == len(lengths) - 1:
            a, b = clean[idx], clean[idx + 1]
            t = left / length if length else 0
            return {
                "name": a.get("city") or a.get("name") if t < 0.08 else b.get("city") or b.get("name") if t > 0.92 else f"{a.get('city') or a.get('name')} to {b.get('city') or b.get('name')}",
                "lat": float(a["lat"]) + (float(b["lat"]) - float(a["lat"])) * t,
                "lng": float(a["lng"]) + (float(b["lng"]) - float(a["lng"])) * t,
                "progress": clamped,
            }
        left -= length
    return {**clean[-1], "progress": 1}


def _candidate_items(guide: dict | None) -> list[dict]:
    if not guide:
        return []
    out = []
    out.extend(guide.get("route_ideas") or [])
    for group in (guide.get("by_type") or {}).values():
        out.extend(group.get("places") or [])
    seen = set()
    deduped = []
    for item in out:
        key = item.get("key") or f"{item.get('source')}:{item.get('name')}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append({**item, "key": key})
    return deduped


def _apply_overrides(items: list[dict], overrides: dict | None, nights: int) -> list[dict]:
    if not overrides:
        return items
    out = []
    for item in items:
        override = overrides.get(item.get("key")) or {}
        part = override.get("part")
        route_progress = override.get("route_progress")
        if part not in PARTS:
            part = None
        try:
            route_progress = float(route_progress)
        except (TypeError, ValueError):
            route_progress = None
        patched = dict(item)
        if part:
            patched["default_part"] = part
            patched["part"] = part
        if route_progress is not None:
            patched["route_progress"] = max(0, min(1, route_progress))
            day = int(patched.get("fixed_day") or patched.get("day") or 1)
            patched["global_route_progress"] = ((day - 1) + patched["route_progress"]) / max(1, nights)
        out.append(patched)
    return out


def _path_distance_to(path: list[dict], target: dict) -> int | None:
    if not target.get("key") or len(path) < 2:
        return None
    total = 0
    for idx in range(1, len(path)):
        total += distance_m(path[idx - 1], path[idx])
        if path[idx].get("key") == target.get("key"):
            return total
    return None


def _slot_item(item: dict, day: int, route_points: list[dict], nights: int) -> dict:
    part = item.get("default_part") or item.get("part") or "afternoon"
    target = PART_RULES.get(part, PART_RULES["afternoon"])["target"]
    local = float(item.get("route_progress") if item.get("route_progress") is not None else target)
    global_progress = float(item.get("global_route_progress") if item.get("global_route_progress") is not None else ((day - 1) + local) / max(1, nights))
    visual = point_at(route_points, global_progress) or {}
    return {
        "key": item.get("key"),
        "name": item.get("name"),
        "part": part,
        "route_progress": round(max(0, min(1, local)), 3),
        "global_route_progress": round(max(0, min(1, global_progress)), 3),
        "actual": {"lat": item.get("lat"), "lng": item.get("lng")} if item.get("lat") is not None and item.get("lng") is not None else None,
        "point": {"lat": visual.get("lat"), "lng": visual.get("lng"), "name": visual.get("name"), "progress": visual.get("progress")},
        "source": item.get("source"),
    }


def build_route_days(itinerary: dict, req: dict, nights: int) -> list[dict]:
    route_points = [p for p in (itinerary.get("route") or []) if _has_point(p)]
    if len(route_points) < 2:
        return []
    raw_items = _candidate_items(itinerary.get("guide"))
    overrides = itinerary.get("route_day_overrides") or {}
    items = _apply_overrides(raw_items, overrides, nights)
    days = []
    completed: list[dict] = []
    previous_end = point_at(route_points, 0)
    for day in range(1, nights + 1):
        day_items = [
            _slot_item(item, day, route_points, nights)
            for item in items
            if int(item.get("fixed_day") or item.get("day") or 0) == day and (item.get("default_part") or item.get("part")) in PARTS
        ]
        day_items.sort(key=lambda x: PARTS.index(x["part"]))
        active_points = []
        if _has_point(previous_end):
            active_points.append({"name": previous_end.get("name") or "Day start", "lat": previous_end["lat"], "lng": previous_end["lng"]})
        for slot in day_items:
            point = slot.get("point") or {}
            if _has_point(point):
                active_points.append({"key": slot["key"], "name": slot["name"], "lat": point["lat"], "lng": point["lng"], "part": slot["part"]})
        for idx, slot in enumerate(day_items):
            slot["distance_from_day_start_m"] = _path_distance_to(active_points, slot)
            prev = active_points[idx] if idx < len(active_points) else None
            curr = active_points[idx + 1] if idx + 1 < len(active_points) else None
            slot["distance_from_previous_stop_m"] = distance_m(prev, curr) if _has_point(prev) and _has_point(curr) else None
        violations = validate_route_day(day_items)
        days.append({
            "day": day,
            "completed_path": list(completed),
            "active_path": active_points,
            "slots": day_items,
            "violations": violations,
            "rules": "docs/ROUTE_DAY_BUSINESS_RULES.md",
        })
        completed.extend(active_points[1:] if completed else active_points)
        if active_points:
            previous_end = active_points[-1]
    return days


def validate_route_day(slots: list[dict]) -> list[str]:
    problems = []
    progresses = [float(s.get("route_progress", 0)) for s in slots]
    if progresses != sorted(progresses):
        problems.append("route_progress_moves_backward")
    by_part = {s.get("part"): s for s in slots}
    for part, rule in PART_RULES.items():
        slot = by_part.get(part)
        if not slot:
            problems.append(f"missing_{part}")
            continue
        lo, hi = rule["band"]
        progress = float(slot.get("route_progress", 0))
        if progress < lo or progress > hi:
            problems.append(f"{part}_outside_route_band")
    return problems
