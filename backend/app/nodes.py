import asyncio
import logging
from datetime import date, timedelta

from . import config
from .live import catalog, llm, osm
from .partners import deals as partner_deals
from .mcp_tools.client import MCPToolClient
from .ranking.combine import rank_and_combine
from .ranking.score import score_flights, score_hotels
from .state import TripState

logger = logging.getLogger(__name__)

# Each node calls a tool by name through the MCP client rather than importing the
# provider function directly — "the AI simply calls tools, no hardcoding," per the
# requirements.


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
        req = state["request"]
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
        req = state["request"]
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
        return {"guide": _with_route_ideas(guide, req) if guide else None, "guide_segments": guides}

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
    itinerary["ai"] = await _ai_summary(itinerary, state)
    return {"itinerary": itinerary}


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
