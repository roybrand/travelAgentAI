import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { fetchConfig, fetchDestinations, planTrip } from "../api";
import { clearStoredProfile, loadProfile, storeProfile } from "../lib/profile";
import { isoDate } from "../lib/format";
import { candidateItems, nextSlot, scheduledItems } from "../lib/dayplan";

const Ctx = createContext(null);
export const useTrip = () => useContext(Ctx);

export function tripDefaults() {
  const start = new Date();
  start.setDate(start.getDate() + 45);
  const end = new Date(start);
  end.setDate(end.getDate() + 7);
  return {
    origin: "LON",
    destination: "TLV",
    start_date: isoDate(start),
    end_date: isoDate(end),
    budget: 2500,
    travelers: 2,
    interests: ["beachfront", "nightlife", "food-scene"],
  };
}

export function TripProvider({ children }) {
  const [form, setForm] = useState(tripDefaults);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [hotelId, setHotelId] = useState(null);
  // The day plan: { [itemKey]: { day, part, order } }. Nothing goes in here except by an explicit action of the
  // traveler's (a tap to add, or a move) — the plan starts empty and nothing is pre-approved for them.
  const [schedule, setSchedule] = useState({});
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
      setSchedule({});
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
    setSchedule({});
    setError("");
    setReadback(null);
    setForm(tripDefaults());
  }, []);

  /** Add or remove an item from the plan. Adding auto-places it (the fewest-filled day, a time of day guessed
   * from its tags); the traveler can move or remove it afterwards on the Day plan tab. Nothing is added without
   * this being called from an explicit tap. */
  const toggleItem = useCallback((item) => {
    const key = item.key || item.name;
    setSchedule((s) => {
      if (s[key]) {
        const next = { ...s };
        delete next[key];
        return next;
      }
      const nights = result?.itinerary?.nights || 1;
      return { ...s, [key]: { ...nextSlot(s, nights, item), order: Date.now() } };
    });
  }, [result]);

  /** Move an already-planned item to a different day or time of day. */
  const moveItem = useCallback((key, day, part) => {
    setSchedule((s) => (s[key] ? { ...s, [key]: { ...s[key], day, part } } : s));
  }, []);

  const trip = useMemo(() => {
    if (!result) return null;
    const { itinerary: it, request: req } = result;
    const hotel = it.hotel_options.find((h) => h.id === hotelId) || it.hotel;
    const candidates = candidateItems(it.guide);
    const chosenItems = scheduledItems(candidates, schedule);
    const flightCost = it.flight.total_price;
    const stayCost = hotel.price_per_night * it.nights;
    const expCost = chosenItems.reduce((sum, i) => sum + (i.cost || 0) * req.travelers, 0);
    const total = flightCost + stayCost + expCost;
    return { it, req, hotel, flightCost, stayCost, expCost, total, chosenItems, candidates, isBest: hotel.id === it.hotel.id };
  }, [result, hotelId, schedule]);

  const planned = trip ? trip.chosenItems.map((i) => i.key) : [];

  const value = {
    form, setForm, result, trip, loading, error, setError, plan, hotelId, setHotelId, planned, toggleItem, moveItem,
    config, destinations, cityName, profile, setProfile, forgetProfile, resetSearch, readback, setReadback,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
