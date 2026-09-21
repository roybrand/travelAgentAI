import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { planTrip } from "../api";
import { isoDate } from "../lib/format";

const Ctx = createContext(null);
export const useTrip = () => useContext(Ctx);

function defaults() {
  const start = new Date();
  start.setDate(start.getDate() + 45);
  const end = new Date(start);
  end.setDate(end.getDate() + 7);
  return {
    origin: "LON",
    destination: "NAP",
    start_date: isoDate(start),
    end_date: isoDate(end),
    budget: 2500,
    travelers: 2,
    interests: ["beachfront", "nightlife", "michelin-nearby"],
  };
}

// Pre-select a few experiences so the trip total is meaningful before the user customises it.
function defaultPlan(guide) {
  if (!guide) return [];
  return [guide.places[0], guide.adventures[0], guide.adventures[1]].filter(Boolean).map((i) => i.name);
}

export function TripProvider({ children }) {
  const [form, setForm] = useState(defaults);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [hotelId, setHotelId] = useState(null);
  const [planned, setPlanned] = useState([]);

  const plan = useCallback(async (payload) => {
    setLoading(true);
    setError("");
    try {
      // Hold the overlay for a moment so the agent steps read as a sequence.
      const [data] = await Promise.all([planTrip(payload), new Promise((r) => setTimeout(r, 2300))]);
      setResult(data);
      setHotelId(data.itinerary.hotel.id);
      setPlanned(defaultPlan(data.itinerary.guide));
      return true;
    } catch (e) {
      setError(e.message || "Something went wrong.");
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  const toggleItem = useCallback(
    (name) => setPlanned((p) => (p.includes(name) ? p.filter((n) => n !== name) : [...p, name])),
    [],
  );

  const trip = useMemo(() => {
    if (!result) return null;
    const { itinerary: it, request: req } = result;
    const hotel = it.hotel_options.find((h) => h.id === hotelId) || it.hotel;
    const items = it.guide ? [...it.guide.places, ...it.guide.adventures] : [];
    const chosenItems = items.filter((i) => planned.includes(i.name));
    const flightCost = it.flight.total_price;
    const stayCost = hotel.price_per_night * it.nights;
    const expCost = chosenItems.reduce((sum, i) => sum + (i.cost || 0) * req.travelers, 0);
    const total = flightCost + stayCost + expCost;
    return { it, req, hotel, flightCost, stayCost, expCost, total, chosenItems, isBest: hotel.id === it.hotel.id };
  }, [result, hotelId, planned]);

  const value = { form, setForm, result, trip, loading, error, setError, plan, hotelId, setHotelId, planned, toggleItem };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
