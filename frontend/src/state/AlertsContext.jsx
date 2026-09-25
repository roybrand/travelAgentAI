import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { request } from "../api";
import { mayNotify, showDeviceNotification } from "../lib/notify";
import { useNearby } from "./NearbyContext.jsx";
import { usePeople } from "./PeopleContext.jsx";
import { useTrip } from "./TripContext.jsx";
import { MOOD } from "../lib/moods";
import { tripPhase } from "../lib/tripday";

const Ctx = createContext(null);
export const useAlerts = () => useContext(Ctx);

const SETTINGS_KEY = "wf.alerts.v1";
const SEEN_KEY = "wf.alerts.seen.v1";
const DEFAULTS = { deals: true, people: true, min_discount: 20, radius_m: 5000, notify: false };
const POLL_MS = 60_000;

const read = (key, fallback) => {
  try {
    return JSON.parse(localStorage.getItem(key) || "null") ?? fallback;
  } catch {
    return fallback;
  }
};
const write = (key, value) => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage may be unavailable */
  }
};

/**
 * The radar: good deals for the trip you planned or the area you are in, and (when signed in to People) matches, requests
 * and messages. It polls the server, remembers which alerts you have seen, and turns new ones into pop-ups, a bell badge
 * and, if allowed, device notifications.
 */
export function AlertsProvider({ children }) {
  const { trip, form, moods } = useTrip();
  const { position, prefs: nearbyPrefs } = useNearby();
  const { token } = usePeople();
  const [settings, setSettingsState] = useState(() => ({ ...DEFAULTS, ...read(SETTINGS_KEY, {}) }));
  const [alerts, setAlerts] = useState([]);
  const [seen, setSeen] = useState(() => new Set(read(SEEN_KEY, [])));
  const [toasts, setToasts] = useState([]);
  const [status, setStatus] = useState("loading");
  const [rss, setRss] = useState("");
  const known = useRef(new Set());
  const first = useRef(true);

  const setSettings = useCallback((patch) => {
    setSettingsState((s) => {
      const next = { ...s, ...patch };
      write(SETTINGS_KEY, next);
      return next;
    });
  }, []);

  const body = useMemo(() => {
    const kinds = [...(settings.deals ? ["deal"] : []), ...(settings.people && token ? ["person", "request", "message"] : [])];
    const gps = nearbyPrefs.enabled && position;
    // During the trip, today's mood (if set) adds what it leans towards to the matching, for today's pop-ups only.
    const phase = trip ? tripPhase(trip.req, trip.it.nights) : null;
    const mood = phase?.phase === "during" ? MOOD[moods[phase.day]] : null;
    const union = (a, b) => [...new Set([...(a || []), ...(b || [])])];
    return {
      dest: trip?.req.destination || form.destination,
      start: trip?.req.start_date, end: trip?.req.end_date,
      interests: union(trip?.req.interests || form.interests, mood?.interests).slice(0, 12),
      place_types: union(trip?.req.place_types, mood?.place_types).slice(0, 14),
      ...(gps ? { lat: Math.round(position.lat * 1000) / 1000, lng: Math.round(position.lng * 1000) / 1000 } : {}),
      radius_m: settings.radius_m, min_discount: settings.min_discount, kinds,
    };
  }, [trip, form.destination, form.interests, position, nearbyPrefs.enabled, settings, token, moods]);
  const bodyKey = JSON.stringify(body);
  const rssUrl = `/api/feed/deals.xml?dest=${body.dest}&interests=${(body.interests || []).join(",")}&min_discount=${settings.min_discount}`;
  useEffect(() => setRss(rssUrl), [rssUrl]);

  const pop = useCallback((list) => {
    const chosen = list.slice(0, 2);
    chosen.forEach((a) => {
      const id = `${a.id}-${Date.now()}`;
      setToasts((t) => [...t.slice(-2), { id, alert: a }]);
      setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 12000);
      if (settings.notify && "Notification" in window && Notification.permission === "granted" && mayNotify(true)) {
        showDeviceNotification({ id: a.id, title: a.title, reason: `${a.badge} · ${a.body}` }, a.link);
      }
    });
  }, [settings.notify]);

  const refresh = useCallback(async () => {
    if (!body.kinds.length) {
      setAlerts([]);
      return setStatus("off");
    }
    try {
      const res = await request("/api/alerts", { method: "POST", body: JSON.parse(bodyKey), token });
      setAlerts(res.alerts);
      setStatus("ok");
      const fresh = res.alerts.filter((a) => !known.current.has(a.id) && !seen.has(a.id));
      res.alerts.forEach((a) => known.current.add(a.id));
      // Do not flood: the first load shows only the single best thing, and later loads show up to two new ones.
      if (fresh.length) pop(first.current ? fresh.slice(0, 1) : fresh);
      first.current = false;
    } catch (e) {
      setStatus(e.status === 401 ? "signin" : "error");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bodyKey, token, pop]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [refresh]);

  const markSeen = useCallback((ids) => {
    setSeen((s) => {
      const next = new Set(s);
      ids.forEach((i) => next.add(i));
      write(SEEN_KEY, [...next].slice(-500));
      return next;
    });
  }, []);
  const dismissToast = useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const unseen = alerts.filter((a) => !seen.has(a.id));

  const value = { alerts, unseen, seen, settings, setSettings, status, refresh, markSeen, toasts, dismissToast, rss };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
