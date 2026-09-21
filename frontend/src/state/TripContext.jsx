import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { fetchConfig, fetchDestinations, planTrip } from "../api";
import { clearStoredProfile, loadProfile, storeProfile } from "../lib/profile";
import { isoDate } from "../lib/format";

const Ctx = createContext(null);
export const useTrip = () => useContext(Ctx);

export function tripDefaults() {
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
    interests: ["beachfront", "nightlife", "food-scene"],
  };
}

// Pre-select a few experiences so the trip total is meaningful before the user customises it.
function defaultPlan(guide) {
  if (!guide) return [];
  return [guide.places[0], guide.adventures[0], guide.adventures[1], guide.places[1]]
    .filter(Boolean)
    .slice(0, 3)
    .map((i) => i.name);
}

export function TripProvider({ children }) {
  const [form, setForm] = useState(tripDefaults);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [hotelId, setHotelId] = useState(null);
  const [planned, setPlanned] = useState([]);
  const [config, setConfig] = useState({ openai: false, amadeus: false, offline: false });
  const [destinations, setDestinations] = useState([]);
  const [profile, setProfileState] = useState(loadProfile);
  // How the last "build from a prompt" was read: which parts came from the words and which from the form.
  const [readback, setReadback] = useState(null);

  useEffect(() => {
    // The server may still be starting when the page first loads, so retry instead of leaving the lists empty.
    let live = true;
    const until = async (fetcher, apply) => {
      for (let i = 0; i < 6 && live; i++) {
        const v = await fetcher();
        if (v) return apply(v);
        await new Promise((r) => setTimeout(r, 1500 * (i + 1)));
      }
    };
    until(fetchConfig, setConfig);
    until(fetchDestinations, (d) => setDestinations(d.destinations));
    return () => {
      live = false;
    };
  }, []);

  const setProfile = useCallback((p) => {
    setProfileState(p);
    if (p) storeProfile(p);
  }, []);
  const forgetProfile = useCallback(() => {
    setProfileState(null);
    clearStoredProfile();
  }, []);

  const cityName = useCallback(
    (code) => destinations.find((d) => d.code === String(code).toUpperCase())?.city || code,
    [destinations],
  );

  const plan = useCallback(async (payload) => {
    setLoading(true);
    setError("");
    try {
      // Hold the overlay briefly so the agent steps read as a sequence; live lookups may take longer.
      // The form and the prompt builder are separate processes: place types come only from what the caller sends.
      const withTypes = { ...payload, place_types: payload.place_types ?? [] };
      const [data] = await Promise.all([planTrip(withTypes), new Promise((r) => setTimeout(r, 2300))]);
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

  /** Forget the current trip and put the search form back to its defaults. The traveler profile is kept. */
  const resetSearch = useCallback(() => {
    setResult(null);
    setHotelId(null);
    setPlanned([]);
    setError("");
    setReadback(null);
    setForm(tripDefaults());
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

  const value = {
    form, setForm, result, trip, loading, error, setError, plan, hotelId, setHotelId, planned, toggleItem,
    config, destinations, cityName, profile, setProfile, forgetProfile, resetSearch, readback, setReadback,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
