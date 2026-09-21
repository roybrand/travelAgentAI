import asyncio
import logging
from datetime import date

from . import config
from .live import catalog, llm
from .partners import deals as partner_deals
from .mcp_tools.client import MCPToolClient
from .ranking.combine import rank_and_combine
from .ranking.score import score_hotels
from .state import TripState

logger = logging.getLogger(__name__)

# Each node calls a tool by name through the MCP client rather than importing the
# provider function directly — "the AI simply calls tools, no hardcoding," per the
# requirements.


def make_search_flights_node(client: MCPToolClient):
    async def node(state: TripState) -> dict:
        req = state["request"]
        result = await client.call("flights", "search_flights", {
            "origin": req["origin"],
            "destination": req["destination"],
            "depart_date": req["start_date"],
            "return_date": req["end_date"],
            "travelers": req["travelers"],
        })
        return {"flights": result["options"], "flights_source": {"mode": result.get("source", "demo"), "detail": result.get("detail", "")}}

    return node


def make_search_hotels_node(client: MCPToolClient):
    async def node(state: TripState) -> dict:
        req = state["request"]
        result = await client.call("hotels", "search_hotels", {
            "destination": req["destination"],
            "check_in": req["start_date"],
            "check_out": req["end_date"],
            "travelers": req["travelers"],
            "interests": req["interests"],
        })
        return {"hotels": result["options"], "hotels_source": {"mode": result.get("source", "demo"), "detail": result.get("detail", "")}}

    return node


def make_destination_guide_node(client: MCPToolClient):
    async def node(state: TripState) -> dict:
        req = state["request"]
        try:
            guide = await client.call("guides", "get_destination_guide", {
                "destination": req["destination"],
                "start_date": req["start_date"],
                "end_date": req["end_date"],
                "interests": req["interests"],
                "place_types": req.get("place_types", []),
            })
        except Exception:
            # The guide is supplementary: a failure here must not sink the whole plan.
            logger.exception("destination guide lookup failed; continuing without it")
            guide = {"found": False}
        return {"guide": guide if guide.get("found") else None}

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

    itinerary = {
        "destination": state["request"]["destination"],
        "nights": state["nights"],
        "flight": chosen["flight"],
        "hotel": chosen["hotel"],
        "total_cost": round(chosen["total_cost"], 2),
        "budget": budget,
        "within_budget": (chosen["total_cost"] <= budget) if budget else None,
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
        "hotel_options": hotel_options,
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
    itinerary["partner_deals"] = _partner_deals(state["request"])
    itinerary["ai"] = await _ai_summary(itinerary, state)
    return {"itinerary": itinerary}


def _partner_deals(req: dict) -> list[dict]:
    """Reviewed partner deals at the destination during the trip, best match first. Supplementary: a database
    problem here must not sink the plan. Ranking is by match to the traveler only (see partners/deals.py)."""
    dest = catalog.resolve(req["destination"])
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
