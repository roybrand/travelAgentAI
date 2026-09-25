import { useEffect, useState } from "react";
import { useTrip } from "../state/TripContext.jsx";
import { PART_LABEL } from "../lib/dayplan";
import { money } from "../lib/format";
import Sheet from "./Sheet.jsx";

/** After booking, a change to paid activities only needs their tickets changing: new ones are charged, dropped ones
 * refunded, moved ones re-dated for free. The flights, the stay and your details stay exactly as booked. */
export default function TicketsSheet({ open, onClose, say }) {
  const { ticketChanges: c, applyTicketChanges, booking } = useTrip();
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (open) {
      setAck(false);
      setError("");
    }
  }, [open]);
  if (!c || !booking) return null;
  const net = c.charge - c.refund;

  const apply = async () => {
    setBusy(true);
    setError("");
    try {
      const r = await applyTicketChanges();
      onClose();
      const money_ = r.charged ? `${money(r.charged)} charged` : r.refunded ? `${money(r.refunded)} refunded` : "no charge";
      say?.(`Tickets updated on ${booking.reference} (${money_}, demo). Flights and stay unchanged`);
    } catch (e) {
      setError(e.message || "The update didn't go through. Nothing was charged.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet
      open={open}
      onClose={busy ? () => {} : onClose}
      title="Update your tickets"
      subtitle={<span className="muted">Booking {booking.reference}. Flights, stay and traveler details stay as they are</span>}
      footer={
        <button type="button" className="btn primary full" disabled={!ack || busy} onClick={apply}>
          {busy ? "Updating…" : net > 0 ? `Update tickets · pay ${money(net)} (demo)` : net < 0 ? `Update tickets · refund ${money(-net)} (demo)` : "Update tickets · no charge"}
        </button>
      }
    >
      <ul className="tk-list">
        {c.added.map((i) => (
          <li key={`a-${i.name}`}><span className="tk-tag add">New</span><b>{i.name}</b><small>Day {i.day} · {PART_LABEL[i.part]}</small><em>+{money(i.cost * c.people)}</em></li>
        ))}
        {c.removed.map((t) => (
          <li key={`r-${t.name}`}><span className="tk-tag remove">Refund</span><b>{t.name}</b><small>{t.code}</small><em>−{money((t.cost ?? 0) * c.people)}</em></li>
        ))}
        {c.moved.map((i) => (
          <li key={`m-${i.name}`}><span className="tk-tag move">Moved</span><b>{i.name}</b><small>now Day {i.day} · {PART_LABEL[i.part]}</small><em>free</em></li>
        ))}
      </ul>
      <p className="fine">Prices are per person × {c.people}. Free activities on your plan never need a ticket.</p>
      <label className="check">
        <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
        <span>I understand this is a demo. Nothing is charged or refunded.</span>
      </label>
      {error && <p className="error" role="alert">{error}</p>}
    </Sheet>
  );
}
