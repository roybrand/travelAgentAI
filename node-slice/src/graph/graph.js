import { StateGraph, END } from "./stateGraph.js";
import {
  searchFlightsNode,
  searchHotelsNode,
  rankAndCombineNode,
  buildItineraryNode,
} from "./nodes.js";

// Orchestration graph for the flights+hotels vertical slice. Flights and
// hotels are independent lookups (no shared state needed between them yet),
// so they run sequentially here; swapping to real LangGraph.js later would
// let them fan out in parallel before the rank/combine join.
export function buildTripPlanningGraph() {
  return new StateGraph()
    .addNode("searchFlights", searchFlightsNode)
    .addNode("searchHotels", searchHotelsNode)
    .addNode("rankAndCombine", rankAndCombineNode)
    .addNode("buildItinerary", buildItineraryNode)
    .setEntryPoint("searchFlights")
    .addEdge("searchFlights", "searchHotels")
    .addEdge("searchHotels", "rankAndCombine")
    .addEdge("rankAndCombine", "buildItinerary")
    .addEdge("buildItinerary", END)
    .compile();
}
