from langgraph.graph import END, START, StateGraph

from .mcp_tools.client import MCPToolClient
from .nodes import (
    build_itinerary_node,
    make_destination_guide_node,
    make_search_flights_node,
    make_search_hotels_node,
    rank_and_combine_node,
)
from .state import TripState


def build_trip_planning_graph(client: MCPToolClient):
    """Flights, stays and the destination guide are independent lookups against separate MCP
    servers, so they fan out in parallel and join before ranking (live sources are slow)."""
    graph = StateGraph(TripState)
    graph.add_node("search_flights", make_search_flights_node(client))
    graph.add_node("search_hotels", make_search_hotels_node(client))
    graph.add_node("destination_guide", make_destination_guide_node(client))
    graph.add_node("rank_and_combine", rank_and_combine_node)
    graph.add_node("build_itinerary", build_itinerary_node)

    for node in ("search_flights", "search_hotels", "destination_guide"):
        graph.add_edge(START, node)
    graph.add_edge(["search_flights", "search_hotels", "destination_guide"], "rank_and_combine")
    graph.add_edge("rank_and_combine", "build_itinerary")
    graph.add_edge("build_itinerary", END)

    return graph.compile()
