import { randomInt, pick } from "../../util/random.js";

const AIRLINES = [
  "BlueSky Air", "Meridian Airlines", "Solara Airways", "Northwind Air",
  "Coastal Jet", "Vantage Airlines", "Aurora Air", "Skyline Express",
];

// Mock provider — stands in for a real Amadeus/Skyscanner-style searchFlights()
// call. Prices/times are randomized on every call so re-invoking the tool
// (i.e. the user pressing "refresh") naturally yields a new plan, matching the
// "re-run search on refresh" behavior described in the requirements.
function searchFlights({ origin, destination, departDate, returnDate, travelers = 1 }) {
  const count = randomInt(4, 6);
  const options = Array.from({ length: count }, (_, i) => {
    const basePrice = randomInt(80, 650);
    const stops = pick([0, 0, 1, 1, 2]);
    const durationMinutes = randomInt(90, 780) + stops * randomInt(45, 120);
    const departHour = randomInt(0, 23);
    const departMinute = pick([0, 15, 30, 45]);

    return {
      id: `FL-${departDate}-${i}-${randomInt(1000, 9999)}`,
      airline: pick(AIRLINES),
      origin,
      destination,
      departDate,
      returnDate,
      stops,
      durationMinutes,
      departTime: `${String(departHour).padStart(2, "0")}:${String(departMinute).padStart(2, "0")}`,
      pricePerTraveler: basePrice,
      totalPrice: basePrice * travelers,
      currency: "GBP",
    };
  });

  return { query: { origin, destination, departDate, returnDate, travelers }, options };
}

export const flightsTool = {
  name: "searchFlights",
  description: "Search for round-trip flight options between an origin and destination for given dates.",
  inputSchema: {
    type: "object",
    required: ["origin", "destination", "departDate", "returnDate"],
    properties: {
      origin: { type: "string" },
      destination: { type: "string" },
      departDate: { type: "string", format: "date" },
      returnDate: { type: "string", format: "date" },
      travelers: { type: "number", default: 1 },
    },
  },
  handler: searchFlights,
};

// exported for tests that want deterministic-ish shape checks without going through the registry
export { searchFlights, AIRLINES };
