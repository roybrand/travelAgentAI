import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { fetchConfig, fetchDestinations, planTrip } from "../api";
import { clearStoredProfile, loadProfile, storeProfile } from "../lib/profile";
import { isoDate } from "../lib/format";
import { candidateItems, nextSlot, scheduledItems } from "../lib/dayplan";
import { loadCurrentTripId, loadTrips, newTripId, storeCurrentTripId, storeTrips } from "../lib/trips";

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

/** The trip that was open when the page was last closed, so a refresh does not lose it. */
function reopenedTrip() {
  const id = loadCurrentTripId();
  return (id && loadTrips().find((t) => t.id === id)) || null;
}

export function TripProvider({ children }) {
  const [initial] = useState(reopenedTrip);
  const [form, setForm] = useState(tripDefaults);
  const [result, setResult] = useState(initial?.result ?? null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [hotelId, setHotelId] = useState(initial?.hotelId ?? null);
  // The day plan: { [itemKey]: { day, part, order } }. Nothing goes in here except by an explicit action of the
  // traveler's (a tap to add, or a move) — the plan starts empty and nothing is pre-approved for them.
  const [schedule, setSchedule] = useState(initial?.schedule ?? {});
  // Saved trips (browser only) and which one is open. Every planned trip is saved; it stays until deleted.
  const [savedTrips, setSavedTrips] = useState(loadTrips);
  const [tripId, setTripId] = useState(initial?.id ?? null);
  const [saveError, setSaveError] = useState("");
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
      const id = newTripId();
      const now = new Date().toISOString();
      setResult(data);
      setHotelId(data.itinerary.hotel.id);
      setSchedule({});
      setTripId(id);
      setSavedTrips((list) => [{ id, savedAt: now, updatedAt: now, result: data, hotelId: data.itinerary.hotel.id, schedule: {} }, ...list]);
      return true;
    } catch (e) {
      setError(e.message || "Something went wrong.");
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  /** Close the current trip (it stays saved) and put the search form back to its defaults. The profile is kept. */
  const resetSearch = useCallback(() => {
    setTripId(null);
    setResult(null);
    setHotelId(null);
    setSchedule({});
    setError("");
    setReadback(null);
    setForm(tripDefaults());
  }, []);

  /** Add or remove an item from the plan. `target` ({ day, part }) is the slot the traveler picked on the Day plan
   * tab; without it (e.g. from Explore) the item goes to the fewest-filled day at a time guessed from its tags. The
   * traveler can move or remove it afterwards. Nothing is added without this being called from an explicit tap. */
  const toggleItem = useCallback((item, target) => {
    const key = item.key || item.name;
    setSchedule((s) => {
      if (s[key]) {
        const next = { ...s };
        delete next[key];
        return next;
      }
      const nights = result?.itinerary?.nights || 1;
      return { ...s, [key]: { ...nextSlot(s, nights, item, target), order: Date.now() } };
    });
  }, [result]);

  // Keep the open trip's saved copy in step with the traveler's choices, and remember which trip is open.
  useEffect(() => {
    if (!tripId) return;
    setSavedTrips((list) => list.map((t) => (t.id === tripId && (t.hotelId !== hotelId || JSON.stringify(t.schedule) !== JSON.stringify(schedule))
      ? { ...t, hotelId, schedule, updatedAt: new Date().toISOString() } : t)));
  }, [tripId, hotelId, schedule]);
  useEffect(() => {
    setSaveError(storeTrips(savedTrips) ? "" : "This browser's storage is full, so the latest changes are not saved. Delete an old trip to make room.");
  }, [savedTrips]);
  useEffect(() => storeCurrentTripId(tripId), [tripId]);

  /** Reopen a saved trip exactly as it was left: its stay and its day plan. */
  const openTrip = useCallback((id) => {
    const t = loadTrips().find((x) => x.id === id) || savedTrips.find((x) => x.id === id);
    if (!t) return false;
    setResult(t.result);
    setHotelId(t.hotelId ?? t.result.itinerary.hotel.id);
    setSchedule(t.schedule || {});
    setError("");
    setReadback(null);
    setTripId(t.id);
    return true;
  }, [savedTrips]);

  /** Give a saved trip a name of the traveler's own ("Honeymoon"); an empty name goes back to the default. */
  const renameTrip = useCallback((id, name) => {
    const clean = (name || "").trim().slice(0, 60);
    setSavedTrips((list) => list.map((t) => (t.id === id ? { ...t, name: clean || null, updatedAt: new Date().toISOString() } : t)));
  }, []);

  /** Save the open trip if it is not saved (e.g. its saved copy was deleted while it stayed open). Returns its id. */
  const saveCurrentTrip = useCallback((name) => {
    if (!result) return null;
    if (tripId && savedTrips.some((t) => t.id === tripId)) return tripId;
    const id = newTripId();
    const now = new Date().toISOString();
    setSavedTrips((list) => [{ id, name: (name || "").trim().slice(0, 60) || null, savedAt: now, updatedAt: now, result, hotelId, schedule }, ...list]);
    setTripId(id);
    return id;
  }, [result, tripId, savedTrips, hotelId, schedule]);

  /** Delete saved trips for good. Deleting the open trip also closes it. */
  const deleteTrips = useCallback((ids) => {
    const gone = new Set(ids);
    setSavedTrips((list) => list.filter((t) => !gone.has(t.id)));
    if (tripId && gone.has(tripId)) {
      setTripId(null);
      setResult(null);
      setHotelId(null);
      setSchedule({});
    }
  }, [tripId]);

  const savedTrip = tripId ? savedTrips.find((t) => t.id === tripId) || null : null;

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
    savedTrips, tripId, savedTrip, openTrip, deleteTrips, renameTrip, saveCurrentTrip, saveError,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
