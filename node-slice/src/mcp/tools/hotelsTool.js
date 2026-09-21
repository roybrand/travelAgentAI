import { randomInt, randomFloat, pick, pickN } from "../../util/random.js";

const HOTEL_PREFIXES = [
  "Grand", "Villa", "The", "Casa", "Palazzo", "Hotel", "Riviera", "Bellavista",
];
const HOTEL_SUFFIXES = [
  "Marina", "Terrace", "Gardens", "Plaza", "Bay", "Suites", "Reale", "Costa",
];

const TAG_POOL = [
  "beachfront", "nightlife", "michelin-nearby", "supercar-rental-nearby",
  "spa", "family-friendly", "old-town", "rooftop-bar", "quiet", "pet-friendly",
];

// Mock provider — stands in for a real Booking.com/Airbnb-style searchHotels()
// call. Tags are the mock stand-in for the "interest matching" scoring the
// requirements describe (beaches, nightlife, Michelin restaurants, etc.).
function searchHotels({ destination, checkIn, checkOut, travelers = 1, interests = [] }) {
  const count = randomInt(5, 8);

  const options = Array.from({ length: count }, (_, i) => {
    const pricePerNight = randomInt(60, 420);
    const rating = randomFloat(3.2, 5.0, 1);
    // bias tag selection so interests show up often enough to matter, but not always
    const guaranteedMatches = interests.filter(() => Math.random() < 0.5);
    const extraTags = pickN(TAG_POOL, randomInt(1, 3));
    const tags = [...new Set([...guaranteedMatches, ...extraTags])];

    return {
      id: `HT-${destination}-${i}-${randomInt(1000, 9999)}`,
      name: `${pick(HOTEL_PREFIXES)} ${pick(HOTEL_SUFFIXES)}`,
      destination,
      checkIn,
      checkOut,
      pricePerNight,
      rating,
      tags,
      distanceToCenterKm: randomFloat(0.1, 8, 1),
      currency: "GBP",
      travelers,
    };
  });

  return { query: { destination, checkIn, checkOut, travelers, interests }, options };
}

export const hotelsTool = {
  name: "searchHotels",
  description: "Search for hotel options in a destination for given check-in/check-out dates, scored against traveler interests.",
  inputSchema: {
    type: "object",
    required: ["destination", "checkIn", "checkOut"],
    properties: {
      destination: { type: "string" },
      checkIn: { type: "string", format: "date" },
      checkOut: { type: "string", format: "date" },
      travelers: { type: "number", default: 1 },
      interests: { type: "array", items: { type: "string" }, default: [] },
    },
  },
  handler: searchHotels,
};

export { searchHotels, TAG_POOL };
