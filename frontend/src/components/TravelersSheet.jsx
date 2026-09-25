import { useEffect, useState } from "react";
import { useTrip } from "../state/TripContext.jsx";
import { money } from "../lib/format";
import Sheet from "./Sheet.jsx";

export const MAX_TRAVELERS = 12; // the same limit as the search form and the booking

/** Change how many people are going. Prices depend on it (a seat each, rooms by occupancy, tickets per person), so
 * this searches again for the same trip, keeping the day plan and, when still offered, the chosen flight and stay. */
export default function TravelersSheet({ open, onClose, say }) {
  const { trip, replanTrip } = useTrip();
  const [n, setN] = useState(trip?.req.travelers || 1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (open && trip) {
      setN(trip.req.travelers);
      setError("");
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!trip) return null;
  const current = trip.req.travelers;
  const was = trip.total;

  const apply = async () => {
    setBusy(true);
    setError("");
    try {
      const kept = await replanTrip({ travelers: n });
      if (!kept) throw new Error("Could not search again.");
      onClose();
      const lost = [!kept.keptFlight && "flight", !kept.keptHotel && "stay"].filter(Boolean);
      say?.(`Now ${n} traveler${n > 1 ? "s" : ""}. Prices searched again (was ${money(was)})${lost.length ? `. Your ${lost.join(" and ")} ${lost.length > 1 ? "weren't" : "wasn't"} offered for ${n}, so the agent's ${lost.length > 1 ? "picks are" : "pick is"} in ${lost.length > 1 ? "their" : "its"} place` : ""}`);
    } catch (e) {
      setError(e.message || "Something went wrong. Nothing was changed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet
      open={open}
      onClose={busy ? () => {} : onClose}
      title="Who's going?"
      subtitle={<span className="muted">Flights, rooms and tickets are priced per person, so we'll search again</span>}
      footer={
        <button type="button" className="btn primary full" disabled={busy || n === current} onClick={apply}>
          {busy ? "Searching prices…" : n === current ? `${current} traveler${current > 1 ? "s" : ""} now` : `Update to ${n} traveler${n > 1 ? "s" : ""}`}
        </button>
      }
    >
      <div className="travelers-pick">
        <button type="button" className="tp-btn" aria-label="Fewer travelers" disabled={busy || n <= 1} onClick={() => setN(n - 1)}>−</button>
        <div className="tp-count"><b>{n}</b><span>traveler{n > 1 ? "s" : ""}</span></div>
        <button type="button" className="tp-btn" aria-label="More travelers" disabled={busy || n >= MAX_TRAVELERS} onClick={() => setN(n + 1)}>+</button>
      </div>
      <ul className="tp-notes">
        <li>Your day plan stays as it is.</li>
        <li>Your flight and stay are kept if they're still offered for {n}; if not, the agent's best match takes their place and we'll tell you.</li>
        {trip.it.nights > 0 && <li>Activity tickets are counted for everyone: {n} × each ticket.</li>}
      </ul>
      {error && <p className="error" role="alert">{error}</p>}
    </Sheet>
  );
}
