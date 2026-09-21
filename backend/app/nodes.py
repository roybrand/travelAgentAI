import logging

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
        return {"flights": result["options"]}

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
        return {"hotels": result["options"]}

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
    return {"itinerary": itinerary}
