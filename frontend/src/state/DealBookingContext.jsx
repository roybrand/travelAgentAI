import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { dealBookings as api } from "../api";
import { useTrip } from "./TripContext.jsx";
import { PARTS, PART_ICON, PART_LABEL } from "../lib/dayplan";
import { dayDate } from "../lib/tripday";
import Sheet from "../components/Sheet.jsx";

const Ctx = createContext(null);
export const useDealBooking = () => useContext(Ctx);

const KEY = "wf.dealBookings.v1";
const load = () => {
  try {
    const list = JSON.parse(localStorage.getItem(KEY) || "[]");
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
};
const store = (list) => {
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    /* storage full or blocked: the booking still happened; it just won't be remembered here */
  }
};

// A sensible time of day for each kind of deal; the traveler can change it.
const CATEGORY_PART = { restaurant: "evening", bar: "night", party: "night", tour: "morning", activity: "afternoon", spa: "afternoon", hotel: "evening", car_rental: "morning", flight: "morning" };
const localToday = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const fmt = (n, currency) => new Intl.NumberFormat("en-GB", { style: "currency", currency: currency || "GBP", maximumFractionDigits: Number.isInteger(n) ? 0 : 2 }).format(n);
const longDay = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });

/** "Book now" on any partner deal, as a demo: pick a day (inside the deal's dates and, when it overlaps, your trip),
 * how many and a time of day. The booking lands in the itinerary on that day. Nothing is reserved or charged. */
export function DealBookingProvider({ children }) {
  const { trip, tripId } = useTrip();
  const [bookings, setBookings] = useState(load);
  const [deal, setDeal] = useState(null); // the deal being booked, or the booking being viewed ({ booking })
  const [form, setForm] = useState({ date: "", quantity: 1, part: "evening", pay: "venue", ack: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(null);

  useEffect(() => store(bookings), [bookings]);

  // The days this deal can be booked on: each trip day inside its dates, or (no overlap) any day inside them.
  const days = useMemo(() => {
    if (!deal || deal.booking) return [];
    const from = [deal.valid_from || localToday(), localToday()].sort()[1];
    const to = deal.valid_to || from;
    if (!trip || from > to) return [];
    const out = [];
    for (let n = 1; n <= trip.it.nights + 1; n++) {
      const iso = dayDate(trip.req.start_date, n);
      if (iso >= from && iso <= to) out.push({ n, iso });
    }
    return out;
  }, [deal, trip]);

  const open = useCallback((d) => {
    setDone(null);
    setError("");
    setDeal(d);
    setForm({ date: "", quantity: 1, part: CATEGORY_PART[d.category] || "evening", pay: "venue", ack: false });
  }, []);
  useEffect(() => {
    if (deal && !deal.booking && !form.date) {
      const from = [deal.valid_from || localToday(), localToday()].sort()[1];
      setForm((f) => ({ ...f, date: days[0]?.iso || from }));
    }
  }, [deal, days, form.date]);

  const openBooking = useCallback((booking) => {
    setError("");
    setDone(null);
    setDeal({ booking });
  }, []);

  const book = async () => {
    setBusy(true);
    setError("");
    try {
      const r = await api.create({ deal_id: deal.id, date: form.date, quantity: form.quantity, pay: form.pay, demo_acknowledged: form.ack });
      const inTrip = trip && form.date >= trip.req.start_date && form.date <= dayDate(trip.req.start_date, trip.it.nights + 1);
      const day = inTrip ? Math.round((new Date(form.date + "T00:00:00") - new Date(trip.req.start_date + "T00:00:00")) / 86400000) + 1 : null;
      const saved = { ...r, part: form.part, tripId: inTrip ? tripId : null, day, bookedAt: new Date().toISOString() };
      setBookings((list) => [saved, ...list]);
      setDone(saved);
    } catch (e) {
      setError(e.message || "The booking didn't go through. Nothing was charged.");
    } finally {
      setBusy(false);
    }
  };

  const cancel = async (b) => {
    if (!window.confirm(`Cancel ${b.deal.title} (${b.reference})? In this demo you get a full refund.`)) return;
    try {
      const r = await api.cancel(b.reference, b.manage_token);
      setBookings((list) => list.map((x) => (x.reference === b.reference ? { ...x, status: r.status, cancelled_at: r.cancelled_at } : x)));
      setDeal(null);
    } catch (e) {
      setError(e.message);
    }
  };

  /** Live (not cancelled) deal bookings for a trip, by trip day. */
  const forTrip = useCallback((id) => bookings.filter((b) => b.tripId && b.tripId === id && b.status !== "cancelled"), [bookings]);

  const viewing = deal?.booking || done;
  const total = deal && !deal.booking ? deal.price * form.quantity : 0;
  const maxQty = Math.min(10, deal?.stock ?? 10);

  const sheet = (
    <Sheet
      open={!!deal}
      onClose={() => { if (!busy) setDeal(null); }}
      title={viewing ? (viewing.status === "cancelled" ? "Booking cancelled" : "You're booked") : "Book now"}
      subtitle={<b className="sheet-item">{viewing ? viewing.deal.title : deal?.title}</b>}
      footer={viewing ? (
        <div className="sheet-actions">
          {viewing.status !== "cancelled" && <button type="button" className="btn ghost danger-btn" onClick={() => cancel(viewing)}>Cancel booking</button>}
          <button type="button" className="btn primary grow" onClick={() => setDeal(null)}>Done</button>
        </div>
      ) : deal && (
        <button type="button" className="btn primary full" disabled={!form.ack || busy || !form.date} onClick={book}>
          {busy ? "Booking…" : form.pay === "now" ? `Book and pay now (demo) · ${fmt(total, deal.currency)}` : `Book now · pay ${fmt(total, deal.currency)} there`}
        </button>
      )}
    >
      {viewing ? (
        <div className="db-done">
          <div className="db-ref"><small>Voucher</small><b>{viewing.voucher || viewing.reference}</b><span>Show this at {viewing.deal.partner_name}. Demo only.</span></div>
          <ul className="db-facts">
            <li>📅 {longDay(viewing.date)}{viewing.part ? ` · ${PART_ICON[viewing.part]} ${PART_LABEL[viewing.part]}` : ""}</li>
            <li>🧾 {viewing.quantity} × {viewing.deal.title}{viewing.deal.price_note ? ` (${viewing.deal.price_note})` : ""} · {fmt(viewing.total, viewing.currency)}</li>
            <li>{viewing.pay === "now" ? `💳 Paid in the app (demo). Nothing to pay at ${viewing.deal.partner_name}` : `🏷️ Pay ${fmt(viewing.total, viewing.currency)} at ${viewing.deal.partner_name} when you arrive. Nothing paid now`}</li>
            {viewing.deal.address && <li>📍 {viewing.deal.address}</li>}
            <li>🔖 Booking {viewing.reference}</li>
          </ul>
          {viewing.day ? <p className="notice ok-notice">Added to your itinerary on Day {viewing.day} · {PART_LABEL[viewing.part]}.</p>
            : <p className="fine">This day isn't part of your open trip, so it isn't in the itinerary.</p>}
          <p className="fine">Demo booking: nothing is reserved with {viewing.deal.partner_name} and nothing is charged.</p>
        </div>
      ) : deal && (
        <div className="db-form">
          <div className="slot-label">Which day</div>
          {days.length > 0 ? (
            <div className="slot-days">
              {days.map(({ n, iso }) => (
                <button key={iso} type="button" className="slot-day" aria-pressed={form.date === iso} onClick={() => setForm({ ...form, date: iso })}>
                  <b>Day {n}</b><span>{longDay(iso)}</span>
                </button>
              ))}
            </div>
          ) : (
            <input className="db-date" type="date" value={form.date} min={[deal.valid_from || localToday(), localToday()].sort()[1]} max={deal.valid_to} onChange={(e) => setForm({ ...form, date: e.target.value })} />
          )}
          <p className="fine">Valid {deal.valid_from ? `${longDay(deal.valid_from)} to ` : "until "}{longDay(deal.valid_to)}{trip && days.length === 0 ? ", which is outside your trip" : ""}.</p>

          <div className="slot-label">Time of day</div>
          <div className="slot-parts">
            {PARTS.map((p) => (
              <button key={p} type="button" className="slot-part" aria-pressed={form.part === p} onClick={() => setForm({ ...form, part: p })}>
                <span aria-hidden="true">{PART_ICON[p]}</span> {PART_LABEL[p]}
              </button>
            ))}
          </div>

          <div className="slot-label">How many</div>
          <div className="db-qty">
            <button type="button" className="tp-btn sm" aria-label="Fewer" disabled={form.quantity <= 1} onClick={() => setForm({ ...form, quantity: form.quantity - 1 })}>−</button>
            <div><b>{form.quantity}</b> × {fmt(deal.price, deal.currency)}{deal.price_note ? <span className="muted"> {deal.price_note}</span> : null}</div>
            <button type="button" className="tp-btn sm" aria-label="More" disabled={form.quantity >= maxQty} onClick={() => setForm({ ...form, quantity: form.quantity + 1 })}>+</button>
          </div>
          {deal.stock != null && <p className="fine">{deal.stock} left, per the business.</p>}

          <div className="slot-label">How you pay</div>
          <div className="pay-pick">
            <button type="button" className="slot-part" aria-pressed={form.pay === "venue"} onClick={() => setForm({ ...form, pay: "venue" })}>
              <span aria-hidden="true">🏷️</span><span><b>At the place</b><small>Show the voucher when you arrive and pay there. The deal price is held for you</small></span>
            </button>
            <button type="button" className="slot-part" aria-pressed={form.pay === "now"} onClick={() => setForm({ ...form, pay: "now" })}>
              <span aria-hidden="true">💳</span><span><b>Now, in the app</b><small>Paid up front, nothing to pay there (demo: no card is charged)</small></span>
            </button>
          </div>

          <label className="check">
            <input type="checkbox" checked={form.ack} onChange={(e) => setForm({ ...form, ack: e.target.checked })} />
            <span>I understand this is a demo. Nothing is reserved with {deal.partner_name} and I won't be charged.</span>
          </label>
          {error && <p className="error" role="alert">{error}</p>}
          <p className="fine">Partner deal, set by the business and reviewed by us. Never ranked by payment.</p>
        </div>
      )}
      {viewing && error && <p className="error" role="alert">{error}</p>}
    </Sheet>
  );

  return (
    <Ctx.Provider value={{ open, openBooking, bookings, forTrip }}>
      {children}
      {sheet}
    </Ctx.Provider>
  );
}
