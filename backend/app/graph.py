from langgraph.graph import END, START, StateGraph

from .mcp_tools.client import MCPToolClient
from .nodes import (
    apply_route_rules_node,
    build_trip_request_node,
    build_itinerary_node,
    make_destination_guide_node,
    make_search_flights_node,
    make_search_hotels_node,
    parse_trip_request_node,
    rank_and_combine_node,
    repair_route_rules_node,
    summarize_itinerary_node,
    validate_itinerary_node,
)
from .state import BuildTripState, ParseRequestState, TripState


def route_rule_next_step(state: TripState) -> str:
    if state.get("planning_rules", {}).get("valid") is True:
        return "done"
    if state.get("route_repair_attempted"):
        return "done"
    return "repair"


def build_trip_planning_graph(client: MCPToolClient):
    """Flights, stays and the destination guide are independent lookups against separate MCP
    servers, so they fan out in parallel and join before ranking (live sources are slow)."""
    graph = StateGraph(TripState)
    graph.add_node("search_flights", make_search_flights_node(client))
    graph.add_node("search_hotels", make_search_hotels_node(client))
    graph.add_node("destination_guide", make_destination_guide_node(client))
    graph.add_node("rank_and_combine", rank_and_combine_node)
    graph.add_node("build_itinerary", build_itinerary_node)
    graph.add_node("summarize_itinerary", summarize_itinerary_node)
    graph.add_node("apply_route_rules", apply_route_rules_node)
    graph.add_node("repair_route_rules", repair_route_rules_node)
    graph.add_node("validate_itinerary", validate_itinerary_node)

    for node in ("search_flights", "search_hotels", "destination_guide"):
        graph.add_edge(START, node)
    graph.add_edge(["search_flights", "search_hotels", "destination_guide"], "rank_and_combine")
    graph.add_edge("rank_and_combine", "build_itinerary")
    graph.add_edge("build_itinerary", "summarize_itinerary")
    graph.add_edge("summarize_itinerary", "apply_route_rules")
    graph.add_conditional_edges("apply_route_rules", route_rule_next_step, {"repair": "repair_route_rules", "done": "validate_itinerary"})
    graph.add_edge("repair_route_rules", "apply_route_rules")
    graph.add_edge("validate_itinerary", END)

    return graph.compile()


def build_parse_request_graph():
    graph = StateGraph(ParseRequestState)
    graph.add_node("parse_trip_request", parse_trip_request_node)
    graph.add_edge(START, "parse_trip_request")
    graph.add_edge("parse_trip_request", END)
    return graph.compile()


def build_trip_request_graph():
    graph = StateGraph(BuildTripState)
    graph.add_node("build_trip_request", build_trip_request_node)
    graph.add_edge(START, "build_trip_request")
    graph.add_edge("build_trip_request", END)
    return graph.compile()
