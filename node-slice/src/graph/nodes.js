import { registry } from "../mcp/registry.js";
import { rankAndCombine } from "../ranking/combine.js";

const MS_PER_DAY = 86_400_000;

export function nightsBetween(startDate, endDate) {
  return Math.max(1, Math.round((new Date(endDate) - new Date(startDate)) / MS_PER_DAY));
}

// Each node calls a tool by name through the MCP-style registry rather than
// importing the provider function directly — "the AI simply calls tools, no
// hardcoding," per the requirements.
export async function searchFlightsNode(state) {
  const { origin, destination, startDate, endDate, travelers } = state.request;
  const result = await registry.call("searchFlights", {
    origin,
    destination,
    departDate: startDate,
    returnDate: endDate,
    travelers,
  });
  return { flights: result.options };
}

export async function searchHotelsNode(state) {
  const { destination, startDate, endDate, travelers, interests } = state.request;
  const result = await registry.call("searchHotels", {
    destination,
    checkIn: startDate,
    checkOut: endDate,
    travelers,
    interests,
  });
  return { hotels: result.options };
}

export async function rankAndCombineNode(state) {
  const nights = nightsBetween(state.request.startDate, state.request.endDate);
  const ranking = rankAndCombine({
    flights: state.flights,
    hotels: state.hotels,
    nights,
    travelers: state.request.travelers ?? 1,
    budget: state.request.budget,
    interests: state.request.interests ?? [],
  });
  return { ranking, nights };
}

export async function buildItineraryNode(state) {
  const { chosen, alternatives, rationale } = state.ranking;
  const budget = state.request.budget ?? null;

  const itinerary = {
    destination: state.request.destination,
    nights: state.nights,
    flight: chosen.flight,
    hotel: chosen.hotel,
    totalCost: Number(chosen.totalCost.toFixed(2)),
    budget,
    withinBudget: budget ? chosen.totalCost <= budget : null,
    rationale,
    alternatives: alternatives.map((alt) => ({
      flight: alt.flight,
      hotel: alt.hotel,
      totalCost: Number(alt.totalCost.toFixed(2)),
      finalScore: Number(alt.finalScore.toFixed(3)),
    })),
  };

  return { itinerary };
}
