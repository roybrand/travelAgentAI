import { useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { useTrip } from "../state/TripContext.jsx";
import { money } from "../lib/format";

/** The bar that stays at the bottom of the trip: an explicit save (on top of the automatic one), what the trip adds
 * up to, and the way on to booking. Rendered into <body>, because the page-transition transform on <main> would
 * otherwise pin a fixed bar to the page instead of the screen. */
export default function PlanBar({ say, onUpdateTickets }) {
  const { trip, savedTrip, saveCurrentTrip, saveError, booking, bookingChanged, ticketChanges } = useTrip();
  const navigate = useNavigate();
  const [flash, setFlash] = useState(false);
  if (!trip) return null;

  const booked = booking && booking.status !== "cancelled";
  const saved = savedTrip && !saveError;
  const save = () => {
    saveCurrentTrip();
    setFlash(true);
    setTimeout(() => setFlash(false), 1800);
    say?.(saveError ? "This browser's storage is full, so the plan could not be saved" : "Saved to My trips. Your plan is kept on this device");
  };
  const n = trip.chosenItems.length;

  return createPortal(
    <div className="dp-bar" role="region" aria-label="Save and book">
      <button type="button" className={`btn sm dp-bar-save ${saved ? "ok" : "primary"} ${flash ? "flash" : ""}`} onClick={save}>
        {saved || flash ? "✓ Saved" : "💾 Save"}
      </button>
      <div className="dp-bar-sum">
        <b>{money(trip.total)}</b>
        <span className="muted">{n} {n === 1 ? "activity" : "activities"} · {booked ? (bookingChanged ? "flight, stay or travelers changed" : ticketChanges ? "tickets to update" : `booked ${booking.reference}`) : "not booked yet"}</span>
      </div>
      {booked && ticketChanges && !bookingChanged ? (
        <button type="button" className="btn primary sm dp-bar-book" onClick={onUpdateTickets}>Update tickets →</button>
      ) : (
        <button type="button" className="btn primary sm dp-bar-book" onClick={() => navigate("/book")}>
          {booked ? (bookingChanged ? "Rebook →" : "Booking →") : "Book trip →"}
        </button>
      )}
    </div>,
    document.body,
  );
}
