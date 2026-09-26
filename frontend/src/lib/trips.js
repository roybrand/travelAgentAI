/** Saved trips live only in this browser (localStorage) and stay until the traveler deletes them. Each entry holds
 * the planner's result plus the traveler's own choices (stay and day plan), so reopening a trip restores it exactly. */
const KEY = "wayfinder.trips.v1";
const CURRENT_KEY = "wayfinder.trips.current";

export function loadTrips() {
  try {
    const list = JSON.parse(localStorage.getItem(KEY) || "[]");
    return Array.isArray(list) ? list.filter((t) => t?.id && t?.result?.itinerary) : [];
  } catch {
    return [];
  }
}

/** Write the whole list. Returns false when the browser refuses (storage full or blocked). */
export function storeTrips(list) {
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
    return true;
  } catch {
    return false;
  }
}

export function loadCurrentTripId() {
  try {
    return localStorage.getItem(CURRENT_KEY) || null;
  } catch {
    return null;
  }
}

export function storeCurrentTripId(id) {
  try {
    if (id) localStorage.setItem(CURRENT_KEY, id);
    else localStorage.removeItem(CURRENT_KEY);
  } catch {
    // Remembering the open trip is a convenience; the trips themselves are unaffected.
  }
}

export const newTripId = () => `t${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

/** Saved trips grouped by destination: groups with the soonest upcoming trip first, trips by start date inside. */
export function groupTrips(trips, today = new Date().toISOString().slice(0, 10)) {
  const groups = new Map();
  trips.forEach((t) => {
    const route = t.result.request.destinations?.length ? t.result.request.destinations : [t.result.request.destination];
    const code = route.join("-");
    if (!groups.has(code)) groups.set(code, { code, trips: [] });
    groups.get(code).trips.push(t);
  });
  const rank = (g) => {
    const upcoming = g.trips.map((t) => t.result.request.start_date).filter((d) => d >= today).sort();
    return upcoming[0] || `~${g.trips.map((t) => t.result.request.start_date).sort().at(-1)}`;
  };
  return [...groups.values()]
    .map((g) => ({ ...g, trips: g.trips.sort((a, b) => a.result.request.start_date.localeCompare(b.result.request.start_date)) }))
    .sort((a, b) => rank(a).localeCompare(rank(b)));
}

/** What a saved trip is called: the traveler's own name for it, else the city and dates. */
export function tripTitle(t, cityName = (c) => c) {
  const req = t.result.request;
  const fmt = (iso) => new Date(iso + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short" });
  const route = (req.destinations?.length ? req.destinations : [req.destination]).map(cityName).join(" → ");
  return t.name || `${route}, ${fmt(req.start_date)} to ${fmt(req.end_date)}`;
}

/** Every flight the traveler can choose from. Trips planned before the full list was sent fall back to the flights
 * they do contain (the agent's pick and its alternatives), without duplicates. */
export function flightOptions(it) {
  if (it.flight_options?.length) return it.flight_options;
  const seen = new Set();
  return [it.flight, ...(it.alternatives || []).map((a) => a.flight)].filter((f) => f && !seen.has(f.id) && seen.add(f.id));
}

/** The flight in use: the traveler's own choice when they made one, else the agent's pick. */
export const pickFlight = (it, id) => flightOptions(it).find((f) => f.id === id) || it.flight;
