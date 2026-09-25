import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { account } from "../api";
import { usePeople } from "./PeopleContext.jsx";
import { useTrip } from "./TripContext.jsx";
import { useDealBooking } from "./DealBookingContext.jsx";
import { loadSync, resetSync, storeSync, tripForSync } from "../lib/sync";

const Ctx = createContext(null);
export const useAccountSync = () => useContext(Ctx);

const CHUNK = 20; // documents sent per request (a trip can be a few hundred KB)

/** Keeps this device's trips and deal bookings in step with the signed-in Wayfinder account. Signed out, nothing
 * leaves the browser. On sign-in, this device's trips move into the account (unless they belonged to a different
 * account that used this browser before), then changes flow both ways: the newest edit wins, deletions travel. */
export function AccountSyncProvider({ children }) {
  const { token, me } = usePeople();
  const { savedTrips, mergeRemoteTrips, forgetLocalTrips } = useTrip();
  const { bookings, mergeRemoteBookings, forgetLocalBookings } = useDealBooking();
  const [status, setStatus] = useState({ state: "off", at: null, error: "" });
  const running = useRef(false);
  const again = useRef(false);
  const latest = useRef({ savedTrips, bookings });
  latest.current = { savedTrips, bookings };

  const syncNow = useCallback(async () => {
    if (!token || !me?.id) return;
    if (running.current) {
      again.current = true; // something changed mid-sync: go once more when this one ends
      return;
    }
    running.current = true;
    setStatus((s) => ({ ...s, state: "syncing", error: "" }));
    try {
      let meta = loadSync();
      if (meta.userId && meta.userId !== me.id) {
        // A different account used this browser before: its synced documents stay in its account, not this one.
        const theirs = Object.keys(meta.pushed);
        forgetLocalTrips(theirs.filter((k) => k.startsWith("trip:")).map((k) => k.slice(5)));
        forgetLocalBookings(theirs.filter((k) => k.startsWith("deal_booking:")).map((k) => k.slice(13)));
        resetSync(me.id);
        meta = loadSync();
        latest.current = {
          savedTrips: latest.current.savedTrips.filter((t) => !theirs.includes(`trip:${t.id}`)),
          bookings: latest.current.bookings.filter((b) => !theirs.includes(`deal_booking:${b.reference}`)),
        };
      }
      meta.userId = me.id;

      const { savedTrips: trips, bookings: deals } = latest.current;
      const outgoing = [
        ...trips.filter((t) => meta.pushed[`trip:${t.id}`] !== t.updatedAt)
          .map((t) => ({ kind: "trip", id: t.id, updated_at: t.updatedAt || t.savedAt, data: tripForSync(t) })),
        ...deals.filter((b) => meta.pushed[`deal_booking:${b.reference}`] !== (b.updatedAt || b.bookedAt))
          .map((b) => ({ kind: "deal_booking", id: b.reference, updated_at: b.updatedAt || b.bookedAt, data: b })),
        ...Object.entries(meta.tombstones).map(([key, at]) => {
          const [kind, ...rest] = key.split(":");
          return { kind, id: rest.join(":"), updated_at: at, deleted: true };
        }),
      ];

      // Send in chunks, then keep reading until the account has nothing newer.
      let i = 0;
      let more = true;
      while (i < outgoing.length || more) {
        const chunk = outgoing.slice(i, i + CHUNK);
        const r = await account.sync(token, meta.seq, chunk);
        chunk.forEach((d) => {
          const key = `${d.kind}:${d.id}`;
          if (d.deleted) delete meta.tombstones[key];
          meta.pushed[key] = d.updated_at;
        });
        mergeRemoteTrips(r.docs.filter((d) => d.kind === "trip"));
        mergeRemoteBookings(r.docs.filter((d) => d.kind === "deal_booking"));
        r.docs.forEach((d) => {
          const key = `${d.kind}:${d.id}`;
          if (d.deleted) delete meta.pushed[key];
          else meta.pushed[key] = d.updated_at;
        });
        meta.seq = r.seq;
        more = r.more;
        i += CHUNK;
        storeSync(meta);
      }
      setStatus({ state: "synced", at: new Date().toISOString(), error: "" });
    } catch (e) {
      setStatus((s) => ({ ...s, state: "error", error: e.status === 401 ? "Please sign in again." : e.message || "Couldn't reach Wayfinder." }));
    } finally {
      running.current = false;
      if (again.current) {
        again.current = false;
        setTimeout(() => syncNow(), 500);
      }
    }
  }, [token, me?.id, mergeRemoteTrips, mergeRemoteBookings, forgetLocalTrips, forgetLocalBookings]);

  // Sync on sign-in, a moment after anything changes, when the app comes back into view, and every minute.
  useEffect(() => {
    if (!token || !me?.id) {
      setStatus({ state: "off", at: null, error: "" });
      return undefined;
    }
    syncNow();
    const every = setInterval(() => document.visibilityState === "visible" && syncNow(), 60000);
    const back = () => document.visibilityState === "visible" && syncNow();
    document.addEventListener("visibilitychange", back);
    return () => {
      clearInterval(every);
      document.removeEventListener("visibilitychange", back);
    };
  }, [token, me?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!token || !me?.id) return undefined;
    const t = setTimeout(() => syncNow(), 2500);
    return () => clearTimeout(t);
  }, [savedTrips, bookings]); // eslint-disable-line react-hooks/exhaustive-deps

  return <Ctx.Provider value={{ ...status, signedIn: !!token && !!me, me, syncNow }}>{children}</Ctx.Provider>;
}
