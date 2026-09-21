import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { fetchNearby } from "../api";
import { distanceM } from "../lib/format";
import { useTrip } from "./TripContext.jsx";

const Ctx = createContext(null);
export const useNearby = () => useContext(Ctx);

const PREFS_KEY = "wf.nearby.v1";
const MOVE_M = 150; // refresh when the user has moved this far
const MAX_AGE_MS = 10 * 60 * 1000; // ...or after this long

function loadPrefs() {
  try {
    return { enabled: false, usePlan: true, notify: false, ...JSON.parse(localStorage.getItem(PREFS_KEY) || "{}") };
  } catch {
    return { enabled: false, usePlan: true, notify: false };
  }
}

/**
 * Opt-in live recommendations. Nothing is requested from the browser until the user turns it on, and the
 * position is only sent to the server to look up places nearby (it is not stored).
 */
export function NearbyProvider({ children }) {
  const { form, trip } = useTrip();
  const [prefs, setPrefs] = useState(loadPrefs);
  const [status, setStatus] = useState("off"); // off | asking | watching | denied | unsupported | insecure | error
  const [position, setPosition] = useState(null);
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [toasts, setToasts] = useState([]);

  const seen = useRef(new Set());
  const last = useRef({ pos: null, at: 0, first: true });
  const ctx = useRef({});
  ctx.current = { form, trip, prefs };

  const savePrefs = useCallback((patch) => {
    setPrefs((p) => {
      const next = { ...p, ...patch };
      try {
        localStorage.setItem(PREFS_KEY, JSON.stringify(next));
      } catch {
        /* storage may be unavailable */
      }
      return next;
    });
  }, []);

  const pushToast = useCallback((rec) => {
    const id = `${rec.id}-${Date.now()}`;
    setToasts((t) => [...t.slice(-2), { id, rec }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 9000);
    if (ctx.current.prefs.notify && "Notification" in window && Notification.permission === "granted") {
      try {
        new Notification(rec.title, { body: rec.reason, tag: rec.id });
      } catch {
        /* some mobile browsers only allow notifications from a service worker */
      }
    }
  }, []);

  const lookup = useCallback(async (pos, force = false) => {
    const now = Date.now();
    const moved = last.current.pos ? distanceM(last.current.pos, pos) : Infinity;
    if (!force && moved < MOVE_M && now - last.current.at < MAX_AGE_MS) return;
    last.current = { ...last.current, pos, at: now };
    const { form: f, trip: t, prefs: p } = ctx.current;
    const planned = p.usePlan && t ? t.chosenItems.filter((i) => i.lat != null).map((i) => ({ name: i.name, lat: i.lat, lng: i.lng })) : [];
    setBusy(true);
    try {
      const res = await fetchNearby({ lat: pos.lat, lng: pos.lng, interests: f.interests, planned });
      setData(res);
      const fresh = res.recommendations.filter((r) => !seen.current.has(r.id));
      fresh.forEach((r) => seen.current.add(r.id));
      // Do not spam on the very first result; push new things as the user moves or conditions change.
      if (!last.current.first) fresh.slice(0, 2).forEach(pushToast);
      last.current.first = false;
      setStatus("watching");
    } catch (e) {
      setStatus("error");
      setData((d) => d || { recommendations: [], notes: [e.message], context: null });
    } finally {
      setBusy(false);
    }
  }, [pushToast]);

  // Start/stop the GPS watcher with the switch.
  useEffect(() => {
    if (!prefs.enabled) {
      setStatus("off");
      return undefined;
    }
    if (!("geolocation" in navigator)) return void setStatus("unsupported");
    if (!window.isSecureContext) return void setStatus("insecure");
    setStatus("asking");
    const id = navigator.geolocation.watchPosition(
      (p) => {
        const pos = { lat: p.coords.latitude, lng: p.coords.longitude, accuracy: p.coords.accuracy };
        setPosition(pos);
        lookup(pos);
      },
      (err) => setStatus(err.code === 1 ? "denied" : "error"),
      { enableHighAccuracy: false, maximumAge: 30000, timeout: 30000 },
    );
    return () => navigator.geolocation.clearWatch(id);
  }, [prefs.enabled, lookup]);

  // Re-rank when the plan or interests change while the feature is on.
  const planKey = trip ? trip.chosenItems.map((i) => i.name).join("|") : "";
  useEffect(() => {
    if (prefs.enabled && position) lookup(position, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planKey, prefs.usePlan, form.interests.join(",")]);

  const requestNotifications = useCallback(async () => {
    if (!("Notification" in window)) return false;
    const perm = Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
    savePrefs({ notify: perm === "granted" });
    return perm === "granted";
  }, [savePrefs]);

  const refresh = useCallback(() => position && lookup(position, true), [position, lookup]);
  const dismiss = useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), []);

  const value = { prefs, savePrefs, status, position, data, busy, toasts, dismiss, refresh, requestNotifications };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
