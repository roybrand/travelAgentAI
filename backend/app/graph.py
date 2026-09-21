from langgraph.graph import END, StateGraph

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
    """Flights and hotels are independent lookups, so they run sequentially here;
    they could fan out in parallel before the rank/combine join if this grows.
    """
    graph = StateGraph(TripState)
    graph.add_node("search_flights", make_search_flights_node(client))
    graph.add_node("search_hotels", make_search_hotels_node(client))
    graph.add_node("destination_guide", make_destination_guide_node(client))
    graph.add_node("rank_and_combine", rank_and_combine_node)
    graph.add_node("build_itinerary", build_itinerary_node)

    graph.set_entry_point("search_flights")
    graph.add_edge("search_flights", "search_hotels")
    graph.add_edge("search_hotels", "destination_guide")
    graph.add_edge("destination_guide", "rank_and_combine")
    graph.add_edge("rank_and_combine", "build_itinerary")
    graph.add_edge("build_itinerary", END)

    return graph.compile()
