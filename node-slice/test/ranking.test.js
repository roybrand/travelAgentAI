import test from "node:test";
import assert from "node:assert/strict";
import { scoreFlights, scoreHotels } from "../src/ranking/score.js";
import { rankAndCombine } from "../src/ranking/combine.js";

const cheapFastFlight = {
  id: "F1", airline: "BlueSky Air", pricePerTraveler: 100, totalPrice: 100,
  durationMinutes: 120, stops: 0,
};
const pricySlowFlight = {
  id: "F2", airline: "Meridian Airlines", pricePerTraveler: 400, totalPrice: 400,
  durationMinutes: 600, stops: 2,
};

const budgetHotelNoMatch = {
  id: "H1", name: "Budget Inn", pricePerNight: 50, rating: 3.0, tags: ["quiet"],
};
const premiumHotelMatch = {
  id: "H2", name: "Grand Marina", pricePerNight: 300, rating: 4.9, tags: ["beachfront", "nightlife"],
};

test("scoreFlights ranks the cheaper, faster flight first", () => {
  const [best, worst] = scoreFlights([pricySlowFlight, cheapFastFlight]);
  assert.equal(best.flight.id, "F1");
  assert.equal(worst.flight.id, "F2");
  assert.ok(best.score > worst.score);
});

test("scoreHotels rewards interest-tag matches", () => {
  const [best] = scoreHotels([budgetHotelNoMatch, premiumHotelMatch], ["beachfront", "nightlife"]);
  assert.equal(best.hotel.id, "H2");
});

test("scoreHotels treats no interests as neutral (0.5) match component", () => {
  const [scoredNoMatch] = scoreHotels([budgetHotelNoMatch], []);
  assert.equal(scoredNoMatch.interestMatch, 0.5);
});

test("rankAndCombine picks the premium combo when budget comfortably allows it", () => {
  const result = rankAndCombine({
    flights: [cheapFastFlight, pricySlowFlight],
    hotels: [budgetHotelNoMatch, premiumHotelMatch],
    nights: 5,
    travelers: 1,
    budget: 5000,
    interests: ["beachfront", "nightlife"],
  });

  assert.equal(result.chosen.flight.id, "F1");
  assert.equal(result.chosen.hotel.id, "H2");
  assert.ok(result.rationale.length >= 1);
});

test("rankAndCombine favors the cheaper combo when budget is tight", () => {
  const result = rankAndCombine({
    flights: [cheapFastFlight, pricySlowFlight],
    hotels: [budgetHotelNoMatch, premiumHotelMatch],
    nights: 5,
    travelers: 1,
    budget: 400, // premium hotel alone (300 * 5 nights) blows this budget
    interests: [],
  });

  assert.equal(result.chosen.hotel.id, "H1");
});

test("rankAndCombine works with no budget specified (budgetFit neutral)", () => {
  const result = rankAndCombine({
    flights: [cheapFastFlight],
    hotels: [premiumHotelMatch],
    nights: 3,
    travelers: 2,
    budget: null,
    interests: [],
  });

  assert.equal(result.chosen.budgetFit, 1);
  assert.equal(result.chosen.totalCost, cheapFastFlight.totalPrice + premiumHotelMatch.pricePerNight * 3);
});
