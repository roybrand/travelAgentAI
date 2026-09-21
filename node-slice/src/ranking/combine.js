import { scoreFlights, scoreHotels, scoreCombo } from "./score.js";

const TOP_N_PER_CATEGORY = 3;

// The "optimize combinations / rank" step from the requirements: take the
// best few flights and best few hotels independently, score every pairing
// together against the trip budget, and return the winner plus alternatives.
export function rankAndCombine({ flights, hotels, nights, travelers, budget, interests }) {
  const topFlights = scoreFlights(flights).slice(0, TOP_N_PER_CATEGORY);
  const topHotels = scoreHotels(hotels, interests).slice(0, TOP_N_PER_CATEGORY);

  const combos = [];
  for (const flightScored of topFlights) {
    for (const hotelScored of topHotels) {
      combos.push(scoreCombo({ flightScored, hotelScored, nights, travelers, budget }));
    }
  }
  combos.sort((a, b) => b.finalScore - a.finalScore);

  const chosen = combos[0];
  const runnerUp = combos.find((c) => c.hotel.id !== chosen.hotel.id) ?? null;

  return {
    chosen,
    alternatives: combos.slice(1, 4),
    rationale: buildRationale(chosen, runnerUp, interests),
  };
}

function buildRationale(chosen, runnerUp, interests) {
  const notes = [];

  notes.push(
    `Total estimated cost £${chosen.totalCost.toFixed(0)} via ${chosen.flight.airline} ` +
    `(${chosen.flight.stops === 0 ? "direct" : `${chosen.flight.stops} stop(s)`}) + ${chosen.hotel.name}.`
  );

  if (runnerUp) {
    const priceDiff = chosen.hotel.pricePerNight - runnerUp.hotel.pricePerNight;
    const ratingDiff = chosen.hotel.rating - runnerUp.hotel.rating;
    const matchedTags = interests.filter((tag) => chosen.hotel.tags.includes(tag));

    const priceClause = priceDiff === 0
      ? "costs the same per night as"
      : `is £${Math.abs(priceDiff).toFixed(0)} ${priceDiff > 0 ? "more" : "less"} per night than`;

    const ratingClause = ratingDiff === 0
      ? "the same rating as"
      : `a ${ratingDiff > 0 ? "higher" : "lower"} rating (${chosen.hotel.rating} vs ${runnerUp.hotel.rating}) than`;

    let sentence = `${chosen.hotel.name} ${priceClause} ${runnerUp.hotel.name}, with ${ratingClause} it.`;
    if (matchedTags.length > 0) {
      sentence += ` It also matches your interests: ${matchedTags.join(", ")}.`;
    }
    notes.push(sentence);
  }

  return notes;
}
