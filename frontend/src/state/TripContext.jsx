import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { bookings as bookingsApi, fetchConfig, fetchDestinations, planTrip } from "../api";
import { clearStoredProfile, loadProfile, storeProfile } from "../lib/profile";
import { isoDate } from "../lib/format";
import { candidateItems, nextSlot, scheduledItems } from "../lib/dayplan";
import { flightOptions, loadCurrentTripId, loadTrips, newTripId, pickFlight, storeCurrentTripId, storeTrips } from "../lib/trips";
import { keepPrivate, recordDeletion } from "../lib/sync";

const Ctx = createContext(null);
export const useTrip = () => useContext(Ctx);

function routeAreaItem(item) {
  return item.source === "route" || item.source === "live-route" || item.area || item.route_stop || item.source === "custom" || item.source === "live-night";
}

function invalidRoutePlace(item) {
  const name = String(item.name || "").toLowerCase().trim();
  return routeAreaItem(item) && ["restaurant", "restaurants", "cafe", "café", "bar", "pub", "park", "museum", "viewpoint", "attraction"].includes(name);
}

function dayLocationsFromTrip(result) {
  const it = result?.itinerary;
  const req = result?.request;
  if (!it || !req) return {};
  const explicit = {};
  (req.day_locations || []).forEach((loc) => {
    if (loc.day && loc.destination) explicit[loc.day] = loc.destination;
  });
  if (Object.keys(explicit).length) return explicit;
  const out = {};
  (it.stay_segments || []).forEach((s) => {
    for (let d = s.start_day; d <= s.end_day; d += 1) out[d] = s.destination;
  });
  const route = req.destinations?.length ? req.destinations : [req.destination];
  if (it.nights) out[it.nights + 1] = route.at(-1) || req.destination;
  return out;
}

export function tripDefaults() {
  const start = new Date();
  start.setDate(start.getDate() + 45);
  const end = new Date(start);
  end.setDate(end.getDate() + 7);
  return {
    origin: "",
    destination: "TLV",
    destinations: ["TLV"],
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
  const [hotelIds, setHotelIds] = useState(initial?.hotelIds ?? {});
  // The traveler's own flight, when they chose one over the agent's pick (null = the agent's pick).
  const [flightId, setFlightId] = useState(initial?.flightId ?? null);
  // The day plan: { [itemKey]: { day, part, order } }. Nothing goes in here except by an explicit action of the
  // traveler's (a tap to add, or a move) — the plan starts empty and nothing is pre-approved for them.
  const [schedule, setSchedule] = useState(initial?.schedule ?? {});
  // The traveler's mood per trip day ({ [day]: moodKey }). It re-orders that day's ideas and deals, nothing else.
  const [moods, setMoods] = useState(initial?.moods ?? {});
  // The traveler's city for each trip day ({ [day]: destinationCode }). Replanning turns this into route stay segments.
  const [dayLocations, setDayLocations] = useState(initial?.dayLocations ?? dayLocationsFromTrip(initial?.result));
  // The traveler's own route/area focus for each day, separate from where they sleep.
  const [dayAreas, setDayAreas] = useState(initial?.dayAreas ?? {});
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
  const routeName = useCallback(
    (req, sep = " → ") => ((req?.destinations?.length ? req.destinations : [req?.destination]).filter(Boolean).map(cityName).join(sep)),
    [cityName],
  );

  const plan = useCallback(async (payload, meta = null) => {
    setLoading(true);
    setError("");
    try {
      // Hold the overlay briefly so the agent steps read as a sequence; live lookups may take longer.
      // The form and the prompt builder are separate processes: place types come only from what the caller sends.
      const route = (payload.destinations?.length ? payload.destinations : [payload.destination]).filter(Boolean);
      const withTypes = { ...payload, destination: route[0] || payload.destination, destinations: route, place_types: payload.place_types ?? [] };
      const [data] = await Promise.all([planTrip(withTypes), new Promise((r) => setTimeout(r, 2300))]);
      const id = newTripId();
      const now = new Date().toISOString();
      const tripReadback = meta?.readback || readback || null;
      setResult(data);
      setHotelId(data.itinerary.hotel.id);
      setHotelIds(Object.fromEntries((data.itinerary.stay_segments || []).map((s) => [s.destination, s.hotel.id])));
      setFlightId(data.itinerary.flight.id);
      setSchedule({});
      setMoods({});
      setDayLocations(dayLocationsFromTrip(data));
      setDayAreas({});
      setReadback(tripReadback);
      setTripId(id);
      setSavedTrips((list) => [{ id, savedAt: now, updatedAt: now, result: data, readback: tripReadback, hotelId: data.itinerary.hotel.id, hotelIds: Object.fromEntries((data.itinerary.stay_segments || []).map((s) => [s.destination, s.hotel.id])), flightId: data.itinerary.flight.id, schedule: {}, dayLocations: dayLocationsFromTrip(data), dayAreas: {} }, ...list]);
      return true;
    } catch (e) {
      setError(e.message || "Something went wrong.");
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  /** Search again for the open trip with some details changed (for now, the number of travelers), because prices
   * depend on them: every traveler needs a seat, rooms are priced by occupancy, tickets are per person. The same trip
   * is updated in place, the day plan is kept, and the chosen flight and stay are kept when they are still offered
   * (matched by id, else by name, or airline, stops and departure time). Returns what was kept, or null on failure. */
  const replanTrip = useCallback(async (changes) => {
    if (!result) return null;
    const req = { ...result.request, ...changes, place_types: changes.place_types ?? result.request.place_types ?? [] };
    const data = await planTrip(req);
    const it = data.itinerary;
    const oldHotel = result.itinerary.hotel_options.find((h) => h.id === hotelId) || result.itinerary.hotel;
    const oldFlight = pickFlight(result.itinerary, flightId);
    const hotel = it.hotel_options.find((h) => h.id === oldHotel.id) || it.hotel_options.find((h) => h.name === oldHotel.name);
    const flight = flightOptions(it).find((f) => f.id === oldFlight.id)
      || flightOptions(it).find((f) => f.airline === oldFlight.airline && f.stops === oldFlight.stops && f.depart_time === oldFlight.depart_time);
    const nextHotel = hotel?.id ?? it.hotel.id;
    const nextHotelIds = Object.fromEntries((it.stay_segments || []).map((s) => {
      const oldId = hotelIds[s.destination];
      const kept = s.hotel_options.find((h) => h.id === oldId) || s.hotel_options.find((h) => h.name === oldHotel.name);
      return [s.destination, kept?.id || s.hotel.id];
    }));
    const nextFlight = flight?.id ?? it.flight.id;
    setResult(data);
    setHotelId(nextHotel);
    setHotelIds(nextHotelIds);
    setFlightId(nextFlight);
    setDayLocations(dayLocationsFromTrip(data));
    // The search form is its own process: a trip change never writes back into it (nor the prompt's profile).
    if (tripId) {
      setSavedTrips((list) => list.map((t) => (t.id === tripId
        ? { ...t, result: data, hotelId: nextHotel, hotelIds: nextHotelIds, flightId: nextFlight, dayLocations: dayLocationsFromTrip(data), updatedAt: new Date().toISOString() } : t)));
    }
    return { keptHotel: !!hotel, keptFlight: !!flight };
  }, [result, hotelId, hotelIds, flightId, tripId]);

  /** Close the current trip (it stays saved) and put the search form back to its defaults. The profile is kept. */
  const resetSearch = useCallback(() => {
    setTripId(null);
    setResult(null);
    setHotelId(null);
    setHotelIds({});
    setFlightId(null);
    setSchedule({});
    setMoods({});
    setDayLocations({});
    setDayAreas({});
    setError("");
    setReadback(null);
    setForm(tripDefaults());
  }, []);

  /** Add or remove an item from the plan. `target` ({ day, part }) is the slot the traveler picked in the shared
   * "when?" sheet or from an exact day/time slot. Without a target, this keeps the legacy least-filled fallback for
   * internal callers only; traveler-facing add buttons should ask for a slot first. */
  const toggleItem = useCallback((item, target) => {
    const key = item.key || item.name;
    setSchedule((s) => {
      if (s[key]) {
        const next = { ...s };
        delete next[key];
        return next;
      }
      const nights = result?.itinerary?.nights || 1;
      const dayDestination = (day) => dayLocations?.[day]
        || (result?.itinerary?.stay_segments || []).find((seg) => day >= seg.start_day && day <= seg.end_day)?.destination
        || result?.request?.destination;
      const matchingDay = item.fixed_day
        || (item.destination ? Array.from({ length: nights }, (_, i) => i + 1).find((day) => dayDestination(day) === item.destination) : null);
      const safeTarget = target || (matchingDay ? { day: matchingDay, part: undefined } : null);
      const snapshot = {
        key,
        name: item.name,
        why: item.why || "",
        source: item.source || "custom",
        type: item.type || null,
        typeLabel: item.typeLabel || null,
        tags: item.tags || [],
        destination: item.destination || null,
        city: item.city || null,
        area: item.area || null,
        route_stop: item.route_stop || null,
        distance_to_route_stop_m: item.distance_to_route_stop_m ?? null,
        distance_to_route_m: item.distance_to_route_m ?? null,
        route_progress: item.route_progress ?? null,
        fixed_day: item.fixed_day || null,
        lat: item.lat ?? null,
        lng: item.lng ?? null,
        photo: item.photo || null,
        photo_url: item.photo_url || null,
        photo_credit: item.photo_credit || null,
        website: item.website || null,
        osm_url: item.osm_url || null,
        url: item.url || null,
        wikipedia: item.wikipedia || null,
        wikidata: item.wikidata || null,
        matches: item.matches || [],
        cost: item.cost ?? null,
        duration: item.duration || null,
      };
      return { ...s, [key]: { ...nextSlot(s, nights, item, safeTarget), item: snapshot, order: Date.now() } };
    });
  }, [result, dayLocations]);

  // Keep the open trip's saved copy in step with the traveler's choices, and remember which trip is open.
  useEffect(() => {
    if (!tripId) return;
    setSavedTrips((list) => list.map((t) => (t.id === tripId && (t.hotelId !== hotelId || JSON.stringify(t.hotelIds || {}) !== JSON.stringify(hotelIds) || t.flightId !== flightId || JSON.stringify(t.schedule) !== JSON.stringify(schedule) || JSON.stringify(t.moods || {}) !== JSON.stringify(moods) || JSON.stringify(t.dayLocations || {}) !== JSON.stringify(dayLocations || {}) || JSON.stringify(t.dayAreas || {}) !== JSON.stringify(dayAreas || {}))
      ? { ...t, hotelId, hotelIds, flightId, schedule, moods, dayLocations, dayAreas, updatedAt: new Date().toISOString() } : t)));
  }, [tripId, hotelId, hotelIds, flightId, schedule, moods, dayLocations, dayAreas]);
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
    setHotelIds(t.hotelIds || Object.fromEntries((t.result.itinerary.stay_segments || []).map((s) => [s.destination, s.hotel.id])));
    setFlightId(t.flightId ?? t.result.itinerary.flight.id);
    setSchedule(t.schedule || {});
    setMoods(t.moods || {});
    setDayLocations(t.dayLocations || dayLocationsFromTrip(t.result));
    setDayAreas(t.dayAreas || {});
    setError("");
    setReadback(t.readback || null);
    setTripId(t.id);
    return true;
  }, [savedTrips]);

  /** Trips arriving from the account (another device changed or deleted them). A newer copy replaces this device's,
   * keeping its private checkout details; the open trip follows along so the page shows the latest version. */
  const mergeRemoteTrips = useCallback((docs) => {
    if (!docs.length) return;
    const byId = new Map(docs.map((d) => [d.id, d]));
    setSavedTrips((list) => {
      const out = [];
      const seen = new Set();
      list.forEach((t) => {
        const d = byId.get(t.id);
        seen.add(t.id);
        if (!d) return out.push(t);
        if (d.deleted) return undefined;
        return out.push(d.updated_at > (t.updatedAt || "") ? keepPrivate(t, d.data) : t);
      });
      docs.forEach((d) => { if (!seen.has(d.id) && !d.deleted && d.data?.result?.itinerary) out.push(d.data); });
      return out.sort((a, b) => (b.savedAt || "").localeCompare(a.savedAt || ""));
    });
    const mine = tripId && byId.get(tripId);
    if (mine?.deleted) {
      setTripId(null);
      setResult(null);
      setHotelId(null);
      setHotelIds({});
      setFlightId(null);
      setSchedule({});
      setMoods({});
      setDayLocations({});
      setDayAreas({});
    } else if (mine?.data?.result) {
      setResult(mine.data.result);
      setHotelId(mine.data.hotelId ?? mine.data.result.itinerary.hotel.id);
      setHotelIds(mine.data.hotelIds || Object.fromEntries((mine.data.result.itinerary.stay_segments || []).map((s) => [s.destination, s.hotel.id])));
      setFlightId(mine.data.flightId ?? mine.data.result.itinerary.flight.id);
      setSchedule(mine.data.schedule || {});
      setMoods(mine.data.moods || {});
      setDayLocations(mine.data.dayLocations || dayLocationsFromTrip(mine.data.result));
      setDayAreas(mine.data.dayAreas || {});
      setReadback(mine.data.readback || null);
    }
  }, [tripId]);

  /** Take trips off this device without recording a deletion (another account signed in; they stay in theirs). */
  const forgetLocalTrips = useCallback((ids) => {
    const gone = new Set(ids);
    setSavedTrips((list) => list.filter((t) => !gone.has(t.id)));
    if (tripId && gone.has(tripId)) {
      setTripId(null);
      setResult(null);
      setHotelId(null);
      setHotelIds({});
      setFlightId(null);
      setSchedule({});
      setMoods({});
      setDayLocations({});
      setDayAreas({});
    }
  }, [tripId]);

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
    setSavedTrips((list) => [{ id, name: (name || "").trim().slice(0, 60) || null, savedAt: now, updatedAt: now, result, readback, hotelId, hotelIds, flightId, schedule, moods, dayLocations, dayAreas }, ...list]);
    setTripId(id);
    return id;
  }, [result, tripId, savedTrips, readback, hotelId, hotelIds, flightId, schedule, moods, dayLocations, dayAreas]);

  /** Delete saved trips for good. Deleting the open trip also closes it. */
  const deleteTrips = useCallback((ids) => {
    const gone = new Set(ids);
    ids.forEach((id) => recordDeletion("trip", id)); // so the deletion reaches the account's other devices
    setSavedTrips((list) => list.filter((t) => !gone.has(t.id)));
    if (tripId && gone.has(tripId)) {
      setTripId(null);
      setResult(null);
      setHotelId(null);
      setHotelIds({});
      setFlightId(null);
      setSchedule({});
      setMoods({});
      setDayLocations({});
      setDayAreas({});
    }
  }, [tripId]);

  const savedTrip = tripId ? savedTrips.find((t) => t.id === tripId) || null : null;

  /** Attach a (demo) booking to the open trip, saving the trip first if needed. The booking keeps a snapshot of the
   * stay and day plan it was made for, so a later change can be flagged. Traveler details live only here. */
  const recordBooking = useCallback((booking) => {
    const id = saveCurrentTrip();
    const snapshot = { hotelId, hotelIds, flightId: pickFlight(result.itinerary, flightId).id, travelers: result.request.travelers, schedule, dayLocations, dayAreas };
    setSavedTrips((list) => list.map((t) => (t.id === id ? { ...t, booking: { ...booking, snapshot }, updatedAt: new Date().toISOString() } : t)));
  }, [saveCurrentTrip, hotelId, hotelIds, flightId, schedule, dayLocations, dayAreas, result]);

  /** Update a trip's booking after a cancel (or a status refresh) from the server. */
  const updateBooking = useCallback((id, patch) => {
    setSavedTrips((list) => list.map((t) => (t.id === id && t.booking ? { ...t, booking: { ...t.booking, ...patch }, updatedAt: new Date().toISOString() } : t)));
  }, []);

  const booking = savedTrip?.booking || null;
  const currentFlightId = result ? pickFlight(result.itinerary, flightId).id : null;
  // Only a new flight, stay or number of travelers means booking again. Day plan changes never do: free activities
  // need nothing, and paid ones are handled as ticket changes (see ticketChanges below).
  const bookingChanged = !!booking && booking.status !== "cancelled" &&
    (booking.snapshot?.hotelId !== hotelId || JSON.stringify(booking.snapshot?.hotelIds || {}) !== JSON.stringify(hotelIds || {}) || (booking.snapshot?.flightId ?? result?.itinerary.flight.id) !== currentFlightId ||
      (booking.snapshot?.travelers ?? result?.request.travelers) !== result?.request.travelers || JSON.stringify(booking.snapshot?.dayLocations || dayLocationsFromTrip(result)) !== JSON.stringify(dayLocations || {}));

  /** Switch to one of the compared flight + stay packages in one go. */
  const choosePackage = useCallback((fid, hid) => {
    setFlightId(fid);
    setHotelId(hid);
    const firstDest = (result?.itinerary.stay_segments || [])[0]?.destination;
    if (firstDest) setHotelIds((m) => ({ ...m, [firstDest]: hid }));
  }, [result]);
  const setHotelForSegment = useCallback((dest, id) => {
    setHotelIds((m) => ({ ...m, [dest]: id }));
    if ((result?.itinerary.stay_segments || [])[0]?.destination === dest) setHotelId(id);
  }, [result]);

  /** Set (or clear, with null) the mood for one trip day. */
  const setMood = useCallback((day, key) => {
    setMoods((m) => {
      const next = { ...m };
      if (key) next[day] = key;
      else delete next[day];
      return next;
    });
  }, []);

  /** Move an already-planned item to a different day or time of day. */
  const moveItem = useCallback((key, day, part) => {
    setSchedule((s) => (s[key] ? { ...s, [key]: { ...s[key], day, part } } : s));
  }, [readback]);

  /** Apply the day-by-day city plan by rerunning the trip search. Consecutive days in the same city become one stay. */
  const applyDayLocations = useCallback(async (locations, dayAreas = null) => {
    const entries = Object.entries(locations || {})
      .map(([day, destination]) => ({ day: Number(day), destination }))
      .filter((x) => x.day && x.destination)
      .sort((a, b) => a.day - b.day);
    const destinations = entries.reduce((list, loc) => (list.at(-1) === loc.destination ? list : [...list, loc.destination]), []);
    return replanTrip({ destination: destinations[0], destinations, day_locations: entries, ...(dayAreas ? { day_areas: dayAreas } : {}) });
  }, [replanTrip]);

  const applyDayFocus = useCallback(async (locations, areas) => {
    const entries = Object.entries(areas || {})
      .map(([day, area]) => ({ day: Number(day), country: area.country || null, label: (area.label || "").trim() }))
      .filter((x) => x.day && (x.country || x.label));
    const kept = await applyDayLocations(locations, entries);
    setDayAreas(areas || {});
    return kept;
  }, [applyDayLocations]);

  const trip = useMemo(() => {
    if (!result) return null;
    const { itinerary: it, request: req } = result;
    const hotel = it.hotel_options.find((h) => h.id === hotelId) || it.hotel;
    const staySegments = (it.stay_segments || []).map((s, idx) => {
      const selected = s.hotel_options.find((h) => h.id === hotelIds[s.destination]) || s.hotel;
      return { ...s, hotel: selected, selectedHotelId: selected.id, primary: idx === 0 };
    });
    const flight = pickFlight(it, flightId);
    const flights = flightOptions(it);
    const candidates = candidateItems(it.guide);
    const dayDestination = (day) => dayLocations?.[day] || staySegments.find((s) => day >= s.start_day && day <= s.end_day)?.destination || req.destination;
    const chosenItems = scheduledItems(candidates, schedule).filter((item) => {
      if (item.fixed_day && item.fixed_day !== item.day) return false;
      if (invalidRoutePlace(item)) return false;
      if (item.destination && item.destination !== dayDestination(item.day)) return false;
      if (dayAreas?.[item.day]?.label?.trim() && !routeAreaItem(item)) return false;
      if (!item.destination && item.segment != null) {
        const seg = staySegments.find((s) => s.index === item.segment);
        if (seg && seg.destination !== dayDestination(item.day)) return false;
      }
      return true;
    });
    const flightCost = flight.total_price;
    const stayCost = staySegments.length ? staySegments.reduce((sum, s) => sum + s.hotel.price_per_night * s.nights, 0) : hotel.price_per_night * it.nights;
    const expCost = chosenItems.reduce((sum, i) => sum + (i.cost || 0) * req.travelers, 0);
    const total = flightCost + stayCost + expCost;
    return {
      it, req, hotel: staySegments[0]?.hotel || hotel, staySegments, dayLocations, dayAreas, flight, flights, flightCost, stayCost, expCost, total, chosenItems, candidates,
      isBest: hotel.id === it.hotel.id, isBestFlight: flight.id === it.flight.id,
    };
  }, [result, hotelId, hotelIds, flightId, schedule, dayLocations, dayAreas]);

  const planned = trip ? trip.chosenItems.map((i) => i.key) : [];

  /** How the paid activities on the plan differ from the tickets already booked: to add (charged), to refund, or
   * to re-date (free). Null when there is nothing to do (no booking, a full rebook is due, or they match). */
  const ticketChanges = useMemo(() => {
    if (!trip || !booking || booking.status === "cancelled" || bookingChanged) return null;
    const people = trip.req.travelers;
    const price = (name) => trip.candidates.find((c) => c.name === name)?.cost || 0;
    const tickets = new Map((booking.tickets || []).map((t) => [t.name, t]));
    const paid = trip.chosenItems.filter((i) => i.cost);
    const added = paid.filter((i) => !tickets.has(i.name));
    const moved = paid.filter((i) => tickets.has(i.name) && (tickets.get(i.name).day !== i.day || tickets.get(i.name).part !== i.part));
    const removed = [...tickets.values()].filter((t) => !paid.some((i) => i.name === t.name));
    if (!added.length && !moved.length && !removed.length) return null;
    const charge = added.reduce((s, i) => s + i.cost * people, 0);
    const refund = removed.reduce((s, t) => s + (t.cost ?? price(t.name)) * people, 0);
    return { added, moved, removed, charge, refund, people };
  }, [trip, booking, bookingChanged]);

  /** Update just the tickets on the booking (demo): nothing else is rebooked and no details are asked again. */
  const applyTicketChanges = useCallback(async () => {
    if (!trip || !booking) return null;
    const activities = trip.chosenItems.map((i) => ({ name: i.name.slice(0, 160), day: i.day, part: i.part, cost: i.cost ?? null }));
    const r = await bookingsApi.updateTickets(booking.reference, booking.manage_token, activities);
    setSavedTrips((list) => list.map((t) => (t.id === tripId && t.booking ? {
      ...t, booking: { ...t.booking, tickets: r.tickets, totals: r.totals, free_activities: trip.chosenItems.filter((i) => !i.cost).map((i) => i.name), snapshot: { ...t.booking.snapshot, schedule, dayLocations, dayAreas } },
      updatedAt: new Date().toISOString(),
    } : t)));
    return r;
  }, [trip, booking, tripId, schedule, dayLocations, dayAreas]);

  const value = {
    form, setForm, result, trip, loading, error, setError, plan, hotelId, setHotelId, hotelIds, setHotelForSegment, flightId, setFlightId, choosePackage, replanTrip, dayLocations, dayAreas, applyDayLocations, applyDayFocus, moods, setMood, planned, toggleItem, moveItem,
    config, destinations, cityName, routeName, profile, setProfile, forgetProfile, resetSearch, readback, setReadback,
    savedTrips, tripId, savedTrip, openTrip, deleteTrips, renameTrip, saveCurrentTrip, saveError, mergeRemoteTrips, forgetLocalTrips,
    booking, bookingChanged, ticketChanges, applyTicketChanges, recordBooking, updateBooking,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
