// Scoring model implementing the "AI ranking" idea from the requirements:
// instead of just picking the cheapest option, score price + quality +
// interest-match + overall budget fit, so a combo that costs a bit more but
// fits the traveler better can outrank the cheapest one.

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function range(values) {
  return { min: Math.min(...values), max: Math.max(...values) };
}

// Higher raw value -> lower score (cheaper/faster wins). Flat range collapses to a neutral 1.
function inverseNormalize(value, { min, max }) {
  if (max === min) return 1;
  return clamp((max - value) / (max - min), 0, 1);
}

export function scoreFlights(flights) {
  const priceRange = range(flights.map((f) => f.pricePerTraveler));
  const durationRange = range(flights.map((f) => f.durationMinutes));

  return flights.map((flight) => {
    const priceScore = inverseNormalize(flight.pricePerTraveler, priceRange);
    const durationScore = inverseNormalize(flight.durationMinutes, durationRange);
    const score = priceScore * 0.6 + durationScore * 0.4;
    return { flight, score, priceScore, durationScore };
  }).sort((a, b) => b.score - a.score);
}

export function scoreHotels(hotels, interests = []) {
  const priceRange = range(hotels.map((h) => h.pricePerNight));

  return hotels.map((hotel) => {
    const priceScore = inverseNormalize(hotel.pricePerNight, priceRange);
    const ratingScore = hotel.rating / 5;
    const interestMatch = interests.length === 0
      ? 0.5
      : interests.filter((tag) => hotel.tags.includes(tag)).length / interests.length;

    const score = priceScore * 0.35 + ratingScore * 0.35 + interestMatch * 0.3;
    return { hotel, score, priceScore, ratingScore, interestMatch };
  }).sort((a, b) => b.score - a.score);
}

export function scoreCombo({ flightScored, hotelScored, nights, travelers, budget }) {
  const totalCost = flightScored.flight.totalPrice + hotelScored.hotel.pricePerNight * nights;
  const budgetFit = budget ? clamp(1 - Math.max(0, totalCost - budget) / budget, 0, 1) : 1;
  const finalScore = flightScored.score * 0.3 + hotelScored.score * 0.5 + budgetFit * 0.2;

  return {
    flight: flightScored.flight,
    hotel: hotelScored.hotel,
    totalCost,
    budgetFit,
    finalScore,
    breakdown: {
      flightScore: flightScored.score,
      hotelScore: hotelScored.score,
      budgetFit,
    },
  };
}

export { clamp, range, inverseNormalize };
