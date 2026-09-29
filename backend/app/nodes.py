import asyncio
import logging
from datetime import date, timedelta
from urllib.parse import urlencode

from . import config
from .live import catalog, llm, osm
from .partners import deals as partner_deals
from . import product_rules, showcase_routes, trip_rules
from . import route_rules
from .mcp_tools.client import MCPToolClient
from .social import demo_people
from .ranking.combine import rank_and_combine
from .ranking.score import score_flights, score_hotels
from .state import BuildTripState, ParseRequestState, TripState

logger = logging.getLogger(__name__)

# Each node calls a tool by name through the MCP client rather than importing the
# provider function directly — "the AI simply calls tools, no hardcoding," per the
# requirements.


async def parse_trip_request_node(state: ParseRequestState) -> dict:
    today = state.get("today") or date.today()
    parsed = await asyncio.to_thread(llm.parse_trip_request, state["text"], today)
    return {"parsed": parsed}


async def build_trip_request_node(state: BuildTripState) -> dict:
    today = state.get("today") or date.today()
    built = await asyncio.to_thread(llm.build_trip, state["text"], state.get("image"), today)
    return {"built": built}


def make_search_flights_node(client: MCPToolClient):
    async def node(state: TripState) -> dict:
        req = state["request"]
        route = req.get("destinations") or [req["destination"]]
        result = await client.call("flights", "search_flights", {
            "origin": req["origin"],
            "destination": route[0],
            "depart_date": req["start_date"],
            "return_date": req["end_date"],
            "travelers": req["travelers"],
        })
        return {"flights": result["options"], "flights_source": {"mode": result.get("source", "demo"), "detail": result.get("detail", "")}}

    return node


def make_search_hotels_node(client: MCPToolClient):
    async def node(state: TripState) -> dict:
        req = showcase_routes.apply_request_defaults(state["request"], state["nights"])
        state["request"] = req
        route = req.get("destinations") or [req["destination"]]
        segments = _day_location_segments(req, state["nights"]) or _segments(route, req["start_date"], state["nights"])
        found = []
        source = None
        for seg in segments:
            result = await client.call("hotels", "search_hotels", {
                "destination": seg["destination"],
                "check_in": seg["check_in"],
                "check_out": seg["check_out"],
                "travelers": req["travelers"],
                "interests": req["interests"],
            })
            options = [{**h, "segment": seg["index"], "segment_destination": seg["destination"], "segment_nights": seg["nights"]} for h in result["options"]]
            found.append({**seg, "options": options})
            source = source or {"mode": result.get("source", "demo"), "detail": result.get("detail", "")}
        return {"hotels": found[0]["options"], "hotel_segments": found, "hotels_source": source or {"mode": "none", "detail": ""}}

    return node


def make_destination_guide_node(client: MCPToolClient):
    async def node(state: TripState) -> dict:
        req = showcase_routes.apply_request_defaults(state["request"], state["nights"])
        state["request"] = req
        if showcase_routes.is_paris_rome_athens(req, state["nights"]):
            guide = showcase_routes.inject_guide(_empty_route_guide(req), req, state["nights"])
            return {"guide": guide, "guide_segments": []}
        route = req.get("destinations") or [req["destination"]]
        guides = []
        for seg in _day_location_segments(req, state["nights"]) or _segments(route, req["start_date"], state["nights"]):
            try:
                guide = await client.call("guides", "get_destination_guide", {
                    "destination": seg["destination"],
                    "start_date": seg["check_in"],
                    "end_date": seg["check_out"],
                    "interests": req["interests"],
                    "place_types": req.get("place_types", []),
                })
            except Exception:
                logger.exception("destination guide lookup failed; continuing without it")
                guide = {"found": False}
            if guide.get("found"):
                guides.append({**seg, "guide": guide})
        guide = _combined_guide(guides) if guides else None
        if not guide and showcase_routes.is_paris_rome_athens(req, state["nights"]):
            guide = _empty_route_guide(req)
        if guide:
            if not showcase_routes.is_paris_rome_athens(req, state["nights"]):
                guide = _with_route_ideas(guide, req)
            guide = showcase_routes.inject_guide(guide, req, state["nights"])
        return {"guide": guide if guide else None, "guide_segments": guides}

    return node


async def rank_and_combine_node(state: TripState) -> dict:
    req = state["request"]
    ranking = rank_and_combine(
        flights=state["flights"],
        hotels=state["hotels"],
        nights=state["nights"],
        budget=req["budget"],
        interests=req["interests"],
    )
    return {"ranking": ranking}


async def build_itinerary_node(state: TripState) -> dict:
    ranking = state["ranking"]
    chosen = ranking["chosen"]
    budget = state["request"]["budget"]

    hotels = state["hotels"]
    prices = [h["price_per_night"] for h in hotels]
    hotel_options = [
        {**s["hotel"], "score": round(s["score"], 3), "interest_match": round(s["interest_match"], 2)}
        for s in score_hotels(hotels, state["request"]["interests"])
    ]

    route = state["request"].get("destinations") or [state["request"]["destination"]]
    stay_segments = _stay_segments(state, chosen)
    stay_total = sum(s["hotel"]["price_per_night"] * s["nights"] for s in stay_segments) if stay_segments else chosen["hotel"]["price_per_night"] * state["nights"]
    total_cost = round(chosen["flight"]["total_price"] + stay_total, 2)
    itinerary = {
        "destination": state["request"]["destination"],
        "destinations": route,
        "route": _route(route),
        "nights": state["nights"],
        "flight": chosen["flight"],
        "hotel": stay_segments[0]["hotel"] if stay_segments else chosen["hotel"],
        "stay_segments": stay_segments,
        "stay_total_cost": round(stay_total, 2),
        "total_cost": total_cost,
        "budget": budget,
        "within_budget": (total_cost <= budget) if budget else None,
        "rationale": ranking["rationale"],
        "pros": chosen["pros"],
        "cons": chosen["cons"],
        "alternatives": [
            {
                "flight": alt["flight"],
                "hotel": alt["hotel"],
                "total_cost": round(alt["total_cost"], 2),
                "final_score": round(alt["final_score"], 3),
                "pros": alt["pros"],
                "cons": alt["cons"],
            }
            for alt in ranking["alternatives"]
        ],
        "guide": state.get("guide"),
        "hotel_options": stay_segments[0]["hotel_options"] if stay_segments else hotel_options,
        "hotel_price_stats": {
            "avg": round(sum(prices) / len(prices)),
            "min": min(prices),
            "max": max(prices),
        },
    }

    guide = state.get("guide")
    guide_sources = "; ".join(v for v in (guide or {}).get("sources", {}).values() if v)
    itinerary["data_sources"] = [
        {"key": "flights", "label": "Flights", **state.get("flights_source", {"mode": "demo", "detail": ""})},
        {"key": "stays", "label": "Stays", **state.get("hotels_source", {"mode": "demo", "detail": ""})},
        {
            "key": "guide", "label": "Season, sights and dining",
            "mode": (guide or {}).get("source", "none") if guide else "none",
            "detail": guide_sources or ("Curated demo content" if guide else "No guide available for this destination"),
        },
    ]
    itinerary["packages"] = _packages(ranking["combos"], chosen)
    itinerary["flight_options"] = _flight_options(state["flights"])
    itinerary["partner_deals"] = _partner_deals(state["request"])
    itinerary["handoff"] = _handoff(state["request"], itinerary)
    itinerary["social"] = _social_layer(state["request"], itinerary)
    return {"itinerary": itinerary}


async def summarize_itinerary_node(state: TripState) -> dict:
    itinerary = dict(state["itinerary"])
    itinerary["ai"] = await _ai_summary(itinerary, state)
    return {"itinerary": itinerary}


async def apply_route_rules_node(state: TripState) -> dict:
    itinerary = dict(state["itinerary"])
    retrieved = product_rules.retrieve("route day map previous completed gray morning noon evening night distances validation")
    route_days = route_rules.build_route_days(itinerary, state["request"], state["nights"])
    violations = [v for day in route_days for v in day.get("violations", [])]
    itinerary["route_days"] = route_days
    itinerary["planning_rules"] = {
        "engine": "deterministic-route-rules",
        "retrieved": retrieved,
        "route_day_violations": violations,
        "valid": not violations,
    }
    if state.get("route_repair"):
        itinerary["planning_rules"]["repair"] = state["route_repair"]
    return {"itinerary": itinerary, "planning_rules": itinerary["planning_rules"]}


async def repair_route_rules_node(state: TripState) -> dict:
    itinerary = dict(state["itinerary"])
    route_days = itinerary.get("route_days") or []
    violations = [v for day in route_days for v in day.get("violations", [])]
    repair = {"attempted": False, "accepted_updates": 0, "reason": "not_needed"}
    if not violations:
        return {"route_repair_attempted": True, "route_repair": repair}
    if not llm.enabled():
        repair["reason"] = "openai_disabled"
        return {"route_repair_attempted": True, "route_repair": repair}

    facts = {
        "violations": violations,
        "rules": itinerary.get("planning_rules", {}).get("retrieved", []),
        "route_days": [
            {
                "day": day.get("day"),
                "violations": day.get("violations", []),
                "slots": [
                    {
                        "key": slot.get("key"),
                        "name": slot.get("name"),
                        "part": slot.get("part"),
                        "route_progress": slot.get("route_progress"),
                    }
                    for slot in day.get("slots", [])
                ],
            }
            for day in route_days
        ],
    }
    repair["attempted"] = True
    repair["reason"] = "llm_candidate"
    try:
        result = await asyncio.wait_for(asyncio.to_thread(llm.repair_route_day_slots, facts), timeout=30)
    except Exception:
        logger.exception("AI route repair failed; continuing with deterministic violations")
        repair["reason"] = "llm_failed"
        return {"route_repair_attempted": True, "route_repair": repair}

    overrides = dict(itinerary.get("route_day_overrides") or {})
    for update in result.get("updates", []):
        overrides[update["key"]] = {"part": update["part"], "route_progress": update["route_progress"]}
    repair["accepted_updates"] = len(result.get("updates", []))
    itinerary["route_day_overrides"] = overrides
    return {"itinerary": itinerary, "route_repair_attempted": True, "route_repair": repair}


async def validate_itinerary_node(state: TripState) -> dict:
    itinerary = dict(state["itinerary"])
    validation = trip_rules.validate_itinerary(itinerary, state["request"], state["nights"])
    itinerary["validation"] = validation
    return {"itinerary": itinerary, "itinerary_validation": validation}


def _partner_deals(req: dict) -> list[dict]:
    """Reviewed partner deals at the destination during the trip, best match first. Supplementary: a database
    problem here must not sink the plan. Ranking is by match to the traveler only (see partners/deals.py)."""
    route = req.get("destinations") or [req["destination"]]
    dest = catalog.resolve(route[0])
    if not dest:
        return []
    try:
        found = partner_deals.for_city(dest["code"], date.fromisoformat(req["start_date"]), date.fromisoformat(req["end_date"]))
        ranked = partner_deals.rank_deals(found, req["interests"], req.get("place_types", []))[:8]
        partner_deals.record_impressions([d["id"] for d in ranked])
        return ranked
    except Exception:
        logger.exception("partner deals lookup failed; continuing without them")
        return []


def _segments(route: list[str], start_iso: str, nights: int) -> list[dict]:
    """Split the trip nights across route stops in order. Extra nights go to earlier stops."""
    usable = route[:max(1, min(len(route), nights))]
    base, extra = divmod(nights, len(usable))
    start = date.fromisoformat(start_iso)
    offset, out = 0, []
    for i, code in enumerate(usable):
        n = base + (1 if i < extra else 0)
        check_in = start + timedelta(days=offset)
        check_out = check_in + timedelta(days=n)
        out.append({"index": i, "destination": code, "nights": n, "check_in": check_in.isoformat(), "check_out": check_out.isoformat()})
        offset += n
    return out


def _day_location_segments(req: dict, nights: int) -> list[dict] | None:
    """Group explicit per-day city choices into hotel nights. Day n means the night after day n; the travel-home day
    can still carry a city label in the request, but it does not create an extra hotel night."""
    picked = {
        int(loc.get("day")): str(loc.get("destination", "")).strip().upper()
        for loc in req.get("day_locations", [])
        if loc.get("day") and loc.get("destination")
    }
    if not picked:
        return None
    days = [picked.get(day) for day in range(1, nights + 1)]
    if any(not code for code in days):
        return None
    start = date.fromisoformat(req["start_date"])
    out, offset = [], 0
    while offset < nights:
        code = days[offset]
        length = 1
        while offset + length < nights and days[offset + length] == code:
            length += 1
        check_in = start + timedelta(days=offset)
        check_out = check_in + timedelta(days=length)
        out.append({"index": len(out), "destination": code, "nights": length, "check_in": check_in.isoformat(), "check_out": check_out.isoformat()})
        offset += length
    return out


def _combined_guide(parts: list[dict]) -> dict:
    first = parts[0]["guide"]
    places, adventures, by_type, sources = [], [], {}, {}
    for part in parts:
        code, guide = part["destination"], part["guide"]
        city = catalog.resolve(code)["city"] if catalog.resolve(code) else code
        for key in ("places", "adventures"):
            for item in guide.get(key, []):
                (places if key == "places" else adventures).append({**item, "destination": code, "city": city, "segment": part["index"]})
        for typ, group in (guide.get("by_type") or {}).items():
            bucket = by_type.setdefault(typ, {**group, "places": []})
            bucket["places"].extend({**p, "destination": code, "city": city, "segment": part["index"]} for p in group.get("places", []))
        sources[code] = "; ".join(v for v in (guide.get("sources") or {}).values() if v) or guide.get("source", "")
    return {**first, "route_guides": parts, "places": places, "adventures": adventures, "by_type": by_type, "sources": sources}


def _empty_route_guide(req: dict) -> dict:
    route = req.get("destinations") or [req["destination"]]
    points = _route(route)
    center_points = [p for p in points if p.get("lat") is not None and p.get("lng") is not None]
    center = [
        sum(p["lat"] for p in center_points) / len(center_points),
        sum(p["lng"] for p in center_points) / len(center_points),
    ] if center_points else None
    return {
        "found": True,
        "name": "Paris to Rome to Athens",
        "source": "showcase",
        "center": center,
        "hero": None,
        "hero_url": None,
        "places": [],
        "adventures": [],
        "by_type": {},
        "sources": {},
        "timing": {"verdict": "Curated 10-day showcase route for testing.", "best_windows": []},
    }


def _stay_segments(state: TripState, chosen: dict) -> list[dict]:
    out = []
    for seg in state.get("hotel_segments", []):
        scored = score_hotels(seg["options"], state["request"]["interests"])
        options = [{**s["hotel"], "score": round(s["score"], 3), "interest_match": round(s["interest_match"], 2)} for s in scored]
        hotel = chosen["hotel"] if seg["index"] == 0 else options[0]
        start_day = 1 + sum(s["nights"] for s in state.get("hotel_segments", [])[:seg["index"]])
        out.append({**{k: seg[k] for k in ("index", "destination", "nights", "check_in", "check_out")},
                    "start_day": start_day, "end_day": start_day + seg["nights"] - 1,
                    "hotel": hotel, "hotel_options": options})
    return out


def _with_route_ideas(guide: dict, req: dict) -> dict:
    """Add day-specific route-corridor attractions from free-text day areas. The normal guide remains intact."""
    if config.offline():
        return guide
    found = []
    for area in req.get("day_areas", []):
        label = str(area.get("label") or "").strip()
        if not label:
            continue
        try:
            corridor = osm.route_attractions(label, area.get("country"), req.get("place_types") or [])
        except Exception:
            logger.exception("route attraction lookup failed; continuing without it")
            continue
        for item in corridor.get("places", []):
            found.append({**item, "day": int(area.get("day") or 0), "area": label, "city": label, "destination": None})
    if not found:
        return guide
    by_type = dict(guide.get("by_type") or {})
    by_type["route"] = {"label": "Along your routes", "places": found}
    sources = dict(guide.get("sources") or {})
    sources["route"] = "OpenStreetMap route waypoint search"
    return {**guide, "route_ideas": found, "by_type": by_type, "sources": sources}


def _route(codes: list[str]) -> list[dict]:
    """Public route labels for the UI. The planner still prices the primary stay in the first stop and travel to the
    final stop, but the request can now represent the full trip route instead of pretending it is one city."""
    out = []
    for code in codes:
        d = catalog.resolve(code)
        out.append({"code": code, "city": d["city"], "country": d["country"], "lat": d.get("lat"), "lng": d.get("lng")} if d else {"code": code, "city": code, "country": ""})
    return out


def _flight_options(flights: list[dict]) -> list[dict]:
    """Every flight found, best value first (the same 60% price / 40% duration score the agent uses), each labelled
    when it is the cheapest, the fastest or the best value, so the traveler can compare and choose their own."""
    if not flights:
        return []
    scored = score_flights(flights)
    cheapest = min(f["total_price"] for f in flights)
    fastest = min(f["duration_minutes"] for f in flights)
    out = []
    for n, s in enumerate(scored):
        f = s["flight"]
        labels = (["Best value"] if n == 0 else []) + (["Cheapest"] if f["total_price"] == cheapest else [])             + (["Fastest"] if f["duration_minutes"] == fastest else [])
        out.append({**f, "score": round(s["score"], 3), "labels": labels})
    return out


def _quality(combo: dict) -> float:
    h = combo["hotel"]
    return h["rating"] if h.get("rating") is not None else (h.get("stars") or 0)


def _packages(combos: list[dict], chosen: dict) -> list[dict]:
    """Three priced options to compare side by side: the cheapest, the agent's best match, and the
    highest-quality stay. When one combination wins several roles it appears once with several labels."""
    picks = [
        ("Cheapest", "Lowest total among the options we scored", min(combos, key=lambda c: c["total_cost"])),
        ("Best match", "The agent's pick for your interests and budget", chosen),
        ("Comfort", "The highest-quality stay we found", max(combos, key=lambda c: (_quality(c), c["total_cost"]))),
    ]
    merged: dict[tuple, dict] = {}
    for label, blurb, c in picks:
        key = (c["flight"]["id"], c["hotel"]["id"])
        if key in merged:
            merged[key]["labels"].append(label)
            continue
        merged[key] = {
            "labels": [label], "blurb": blurb, "flight": c["flight"], "hotel": c["hotel"],
            "total_cost": round(c["total_cost"], 2),
            "vs_best": round(c["total_cost"] - chosen["total_cost"], 2),
            "price_sources": {"flight": c["flight"].get("price_source", "demo"), "hotel": c["hotel"].get("price_source", "demo")},
        }
    return list(merged.values())


def _search_url(query: str) -> str:
    return "https://www.google.com/search?" + urlencode({"q": query})


def _handoff(req: dict, itinerary: dict) -> dict:
    """Trusted external booking actions. Wayfinder plans and explains; airlines, hotels and partners own checkout."""
    route = req.get("destinations") or [req["destination"]]
    first = route[0]
    final = route[-1]
    flight = itinerary["flight"]
    hotel = itinerary["hotel"]
    first_city = catalog.resolve(first)["city"] if catalog.resolve(first) else first
    final_city = catalog.resolve(final)["city"] if catalog.resolve(final) else final
    origin_city = catalog.resolve(req["origin"])["city"] if catalog.resolve(req["origin"]) else req["origin"]
    flight_query = f"{origin_city} to {first_city} return flights {req['start_date']} {req['end_date']} {req['travelers']} travelers"
    stay_query = f"{hotel['name']} {first_city} hotel {req['start_date']} {req['end_date']} {req['travelers']} guests"
    return {
        "model": "planner_handoff",
        "principle": "Wayfinder plans, validates and monitors the trip. Flight and stay checkout stays with trusted external sellers.",
        "flight": {
            "kind": "external_checkout",
            "title": f"{origin_city} to {first_city}{'' if final == first else f', return from {final_city}'}",
            "provider": "Airline or flight marketplace",
            "url": _search_url(flight_query),
            "owned_by_wayfinder": False,
            "affiliate_ready": True,
            "price_scope": "Shown for all travelers, return trip. Confirm baggage, fare class, refund rules and schedule changes before paying.",
            "source": flight.get("price_source", itinerary.get("data_sources", [{}])[0].get("mode", "demo")),
        },
        "stay": {
            "kind": "external_checkout",
            "title": hotel["name"],
            "provider": "Hotel site or lodging marketplace",
            "url": hotel.get("website") or _search_url(stay_query),
            "owned_by_wayfinder": False,
            "affiliate_ready": True,
            "price_scope": f"Shown as nightly rate x {itinerary['nights']} night{'' if itinerary['nights'] == 1 else 's'}. Confirm taxes, fees, cancellation and room type before paying.",
            "source": hotel.get("price_source", itinerary.get("data_sources", [{}, {}])[1].get("mode", "demo")),
        },
        "local_marketplace": {
            "kind": "wayfinder_partner_vouchers",
            "title": "Local deals, activities and transfers",
            "owned_by_wayfinder": True,
            "phase": "partner_deals_first",
            "price_scope": "Only reviewed partner deals can be reserved in Wayfinder. Flights and stays are handoff-only.",
        },
    }


SOCIAL_ACTIVITY_MAP = {
    "nightlife": ("nightlife", "evening", "Find travelers for drinks or nightlife near {place}"),
    "live-music": ("live-music", "night", "Find travelers for live music near {place}"),
    "food-scene": ("food", "evening", "Find travelers for dinner or street food near {place}"),
    "michelin-nearby": ("food", "evening", "Find travelers for a special dinner near {place}"),
    "old-town": ("sightseeing", "afternoon", "Find travelers to explore {place}"),
    "beachfront": ("beach", "afternoon", "Find travelers for the beach near {place}"),
    "spa": ("yoga", "morning", "Find travelers for wellness or a spa morning near {place}"),
    "quiet": ("coffee", "morning", "Find travelers for coffee and an easy walk near {place}"),
}


def _social_layer(req: dict, itinerary: dict) -> dict:
    """Trip-aware social hooks. People matching stays its own product surface, but the graph now emits
    ready-to-use prompts so the itinerary can become the social onboarding engine."""
    route = req.get("destinations") or [req["destination"]]
    city = catalog.resolve(route[0])
    city_name = city["city"] if city else route[0]
    prompts, seen = [], set()
    interests = req.get("interests") or []
    for interest in interests:
        mapped = SOCIAL_ACTIVITY_MAP.get(interest)
        if not mapped:
            continue
        tag, part, template = mapped
        if tag in seen:
            continue
        seen.add(tag)
        prompts.append({
            "id": f"interest:{tag}",
            "source": "trip_interest",
            "day": 1,
            "part": part,
            "destination": route[0],
            "activity_tag": tag,
            "title": template.format(place=city_name),
            "text": f"{template.format(place=city_name)} during my trip. Someone friendly with shared travel interests.",
        })
    guide = itinerary.get("guide") or {}
    for item in (guide.get("places") or [])[:8]:
        tags = set(item.get("tags") or [])
        tag = "sightseeing"
        if {"food-scene", "restaurant", "dining"} & tags:
            tag = "food"
        elif {"nightlife", "bar"} & tags:
            tag = "nightlife"
        elif {"beachfront", "beach"} & tags:
            tag = "beach"
        if tag in seen:
            continue
        seen.add(tag)
        name = item.get("name") or city_name
        prompts.append({
            "id": f"place:{item.get('key') or name}",
            "source": "itinerary_place",
            "day": item.get("fixed_day") or 1,
            "part": item.get("default_part") or ("evening" if tag in {"food", "nightlife"} else "afternoon"),
            "destination": item.get("destination") or route[0],
            "activity_tag": tag,
            "title": f"Find travelers for {name}",
            "text": f"Find travelers who want to visit {name} with me. Keep it public, easy and friendly.",
        })
        if len(prompts) >= 5:
            break
    if not prompts:
        prompts.append({
            "id": "default:coffee",
            "source": "trip_default",
            "day": 1,
            "part": "evening",
            "destination": route[0],
            "activity_tag": "coffee",
            "title": f"Find travelers in {city_name}",
            "text": f"Coffee or a relaxed walk in {city_name}, someone friendly who wants to explore.",
        })
    stay_segments = itinerary.get("stay_segments") or []
    days = []
    for day in range(1, itinerary.get("nights", 0) + 1):
        segment = next((s for s in stay_segments if s.get("start_day", 1) <= day <= s.get("end_day", 1)), None)
        code = (segment or {}).get("destination") or route[min(day - 1, len(route) - 1)]
        dest = catalog.resolve(code)
        label = dest["city"] if dest else code
        day_prompts = [{**p, "day": day, "destination": code} for p in prompts if p.get("destination") in {code, route[0]}][:3]
        if not day_prompts:
            day_prompts = [{
                "id": f"day:{day}:coffee",
                "source": "trip_day_default",
                "day": day,
                "part": "evening",
                "destination": code,
                "activity_tag": "coffee",
                "title": f"Find travelers in {label}",
                "text": f"Coffee, food or an easy walk in {label} on day {day}, someone friendly with shared hobbies.",
            }]
        days.append({
            "day": day,
            "destination": code,
            "city": label,
            "headline": f"Light up Day {day} in {label}",
            "summary": "Find people on your route who want similar company, hobbies and plans.",
            "prompts": day_prompts,
        })
    try:
        companions = demo_people.seed_route_companions(days, req["start_date"])
        for day in days:
            day["companions"] = companions.get(day["day"], [])
    except Exception:
        logger.exception("route companion demo seeding failed; continuing without route people")
        for day in days:
            day["companions"] = []
    return {
        "positioning": "Use the itinerary as social context: who overlaps with this place, date, activity and vibe?",
        "prompts": prompts[:5],
        "days": days,
        "density_goal": "Show a small set of relevant people or plans fast; if density is low, suggest place check-ins and local group activities.",
    }


def _human_date(iso: str) -> str:
    """'2026-12-05' -> '5 December 2026', so the model can copy it without reformatting digits."""
    d = date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%B %Y')}"


async def _ai_summary(itinerary: dict, state: TripState) -> dict | None:
    """Optional OpenAI-written summary, grounded in the facts below. Any failure just means no summary."""
    if not llm.enabled():
        return None
    req, guide, flight, hotel = state["request"], itinerary.get("guide"), itinerary["flight"], itinerary["hotel"]
    facts = {
        "destination": (guide or {}).get("name") or req["destination"],
        "dates": f"{_human_date(req['start_date'])} to {_human_date(req['end_date'])}",
        "nights": itinerary["nights"],
        "travelers": req["travelers"],
        "budget": req["budget"],
        "estimated_total_flights_and_stay": itinerary["total_cost"],
        "flight": {"stops": flight["stops"], "total": flight["total_price"], "price_source": flight.get("price_source", "demo")},
        "hotel": {
            "name": hotel["name"], "stars": hotel.get("stars"), "price_per_night": hotel["price_per_night"],
            "price_source": hotel.get("price_source", "demo"), "km_from_centre": hotel.get("distance_to_center_km"),
        },
        "pros": itinerary["pros"][:4],
        "cons": itinerary["cons"][:3],
    }
    if guide:
        facts["season"] = {"verdict_for_these_dates": guide["timing"]["verdict"], "best_months": guide["timing"]["best_windows"]}
        facts["top_sights"] = [p["name"] for p in guide["places"][:4]]
    try:
        text = await asyncio.wait_for(asyncio.to_thread(llm.summarize, facts), timeout=30)
    except Exception:
        logger.exception("AI summary failed; continuing without it")
        return None
    return {"summary": text, "model": config.openai_model()} if text else None
