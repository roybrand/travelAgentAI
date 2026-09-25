import { useEffect, useRef, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { useTrip } from "../state/TripContext.jsx";
import { bookings } from "../api";
import { PART_LABEL } from "../lib/dayplan";
import { duration, longDate, money } from "../lib/format";
import { tripCalendar, downloadCalendar } from "../lib/ics";
import BackLink from "../components/BackLink.jsx";
import SourceBadge from "../components/SourceBadge.jsx";
import TravelersSheet from "../components/TravelersSheet.jsx";

const STEPS = [["review", "Review"], ["travelers", "Travelers"], ["pay", "Payment"], ["done", "Confirmed"]];
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

function Stepper({ step }) {
  const at = STEPS.findIndex(([k]) => k === step);
  return (
    <ol className="bk-steps" aria-label="Booking steps">
      {STEPS.map(([k, label], i) => (
        <li key={k} className={i < at ? "done" : i === at ? "on" : ""} aria-current={i === at ? "step" : undefined}>
          <span className="bk-steps-dot">{i < at ? "✓" : i + 1}</span>
          <span className="bk-steps-label">{label}</span>
        </li>
      ))}
    </ol>
  );
}

function Line({ icon, title, sub, amount, badge }) {
  return (
    <div className="bk-line">
      <span className="bk-icon" aria-hidden="true">{icon}</span>
      <div className="bk-line-body"><b>{title}</b>{sub && <small>{sub}</small>}</div>
      <div className="bk-amount">{amount}{badge}</div>
    </div>
  );
}

/** The whole booking journey for the open trip -- review, traveler details, payment, confirmation -- as a demo:
 * nothing is reserved with an airline or hotel and nothing is charged, and every step says so. */
export default function Book() {
  const { trip, cityName, booking, bookingChanged, recordBooking, updateBooking, tripId } = useTrip();
  const [step, setStep] = useState(booking && !bookingChanged ? "done" : "review");
  const [who, setWho] = useState(() => booking?.lead ? { ...booking.lead, others: booking.others || [] } : { name: "", email: "", phone: "", others: [] });
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(-1);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [travelersOpen, setTravelersOpen] = useState(false);
  const [changeNote, setChangeNote] = useState("");
  const counted = useRef(false);

  useEffect(() => {
    if (!counted.current && !(booking && !bookingChanged)) {
      counted.current = true;
      bookings.checkout();
    }
  }, [booking, bookingChanged]);
  // Braces matter: newer browsers return a Promise from scrollTo, and React would call it as a cleanup function.
  useEffect(() => { window.scrollTo({ top: 0, behavior: "smooth" }); }, [step]);

  if (!trip) return <Navigate to="/" replace />;
  const { it, req, hotel, flight, flightCost, stayCost, expCost, total, chosenItems } = trip;
  const from = cityName(req.origin);
  const to = cityName(req.destination);
  const nights = it.nights;
  const stops = flight.stops === 0 ? "Direct" : `${flight.stops} stop${flight.stops > 1 ? "s" : ""}`;
  const paid = chosenItems.filter((i) => i.cost);
  const free = chosenItems.filter((i) => !i.cost);
  const others = Array.from({ length: Math.max(0, req.travelers - 1) }, (_, i) => who.others[i] || "");
  const live = booking && booking.status !== "cancelled";

  const PROGRESS = [
    "Checking your prices",
    `Holding ${req.travelers} seat${req.travelers > 1 ? "s" : ""} ${flight.airline ? `with ${flight.airline}` : "on your flight"}`,
    `Reserving your room at ${hotel.name}`,
    paid.length ? `Issuing ${paid.length} activity ticket${paid.length > 1 ? "s" : ""}` : "Adding your day plan",
    "Writing your confirmation",
  ];

  const confirm = async () => {
    setBusy(true);
    setError("");
    setProgress(0);
    const payload = {
      origin: req.origin, destination: req.destination, start_date: req.start_date, end_date: req.end_date, travelers: req.travelers,
      flight: { airline: flight.airline || "", depart_time: flight.depart_time || null, stops: flight.stops || 0, total_price: flightCost, price_source: flight.price_source || "demo" },
      stay: { name: hotel.name, price_per_night: hotel.price_per_night, price_source: hotel.price_source || "demo" },
      activities: chosenItems.map((i) => ({ name: i.name.slice(0, 160), day: i.day, part: i.part, cost: i.cost ?? null })),
      demo_acknowledged: ack,
    };
    try {
      // Replacing a booking made before the plan changed: cancel the old one first, as a real rebooking would.
      if (live && bookingChanged) await bookings.cancel(booking.reference, booking.manage_token).catch(() => {});
      const call = bookings.create(payload);
      for (let i = 1; i < PROGRESS.length; i++) {
        await wait(650);
        setProgress(i);
      }
      const result = await call;
      await wait(500);
      recordBooking({ ...result, lead: { name: who.name, email: who.email, phone: who.phone }, others: others });
      setStep("done");
    } catch (e) {
      setError(e.message || "The booking did not go through. Nothing was charged. Please try again.");
    } finally {
      setBusy(false);
      setProgress(-1);
    }
  };

  const cancel = async () => {
    if (!window.confirm(`Cancel booking ${booking.reference}? In this demo you get a full refund.`)) return;
    try {
      const r = await bookings.cancel(booking.reference, booking.manage_token);
      updateBooking(tripId, { status: r.status, cancelled_at: r.cancelled_at });
    } catch (e) {
      setError(e.message);
    }
  };

  const calendar = () => downloadCalendar(
    tripCalendar({ reference: booking.reference, req, cityFrom: from, cityTo: to, hotel, flight, items: chosenItems, booking }),
    `wayfinder-${booking.reference}.ics`,
  );
  const copyRef = () => navigator.clipboard?.writeText(booking.reference).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1800); }).catch(() => {});

  const summary = (
    <div className="bk-summary card pad">
      <div className="bk-trip">
        <div>
          <div className="eyebrow">{from} → {to}</div>
          <b>{longDate(req.start_date)} – {longDate(req.end_date)}</b>
          <div className="muted">{nights} night{nights > 1 ? "s" : ""} · {req.travelers} traveler{req.travelers > 1 ? "s" : ""} · <button type="button" className="linkbtn" onClick={() => setTravelersOpen(true)}>change</button></div>
        </div>
      </div>
      <Line icon="✈️" title={`${flight.airline || "Flights"} · ${stops}`} sub={[`Return, ${from} ⇄ ${to}`, flight.duration_minutes && duration(flight.duration_minutes), flight.depart_time && `departs ${flight.depart_time}`].filter(Boolean).join(" · ")} amount={money(flightCost)} badge={<SourceBadge mode={flight.price_source} />} />
      <Line icon="🏨" title={hotel.name} sub={`${nights} night${nights > 1 ? "s" : ""} × ${money(hotel.price_per_night)}`} amount={money(stayCost)} badge={<SourceBadge mode={hotel.price_source} />} />
      {paid.length > 0 && (
        <div className="bk-acts">
          <div className="bk-acts-h">🎟️ Activity tickets</div>
          {paid.map((i) => (
            <div key={i.key} className="bk-act">
              <span>Day {i.day} · {PART_LABEL[i.part]}</span>
              <b>{i.name}</b>
              <em>{req.travelers} × {money(i.cost)}</em>
            </div>
          ))}
          <div className="bk-act total"><span /><b>Activities</b><em>{money(expCost)}</em></div>
        </div>
      )}
      {free.length > 0 && <p className="fine">Also on your plan, free with no ticket: {free.map((i) => i.name).join(", ")}.</p>}
      <div className="bk-total">
        <span>Total</span>
        <b>{money(total)}</b>
      </div>
      <p className="fine">{money(Math.round(total / req.travelers))} per person. Prices marked Estimate or Demo are modelled from free data, not quoted by the airline or hotel.</p>
    </div>
  );

  return (
    <div className="wrap page narrow book-page">
      <BackLink fallback="/trip" />
      <div className="demo-flag" role="note">
        <b>Demo booking.</b> Nothing is reserved with any airline, hotel or venue, and nothing is charged. It shows the whole booking process from start to finish.
      </div>
      <Stepper step={step} />

      <AnimatePresence mode="wait">
        <motion.div key={step} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.22 }}>
          {step === "review" && (
            <>
              <h1 className="h2">Review your trip</h1>
              {changeNote && <p className="notice">{changeNote}</p>}
              {live && bookingChanged && (
                <p className="notice">You changed your stay or day plan after booking <b>{booking.reference}</b>. Book again to replace it. The old demo booking is cancelled automatically.</p>
              )}
              {summary}
              {!chosenItems.length && <p className="notice">No activities on your plan yet. You can still book the flight and stay, or <Link to="/trip">add some first</Link>.</p>}
              <div className="bk-actions">
                <Link to="/trip" className="btn ghost">✎ Edit itinerary</Link>
                <Link to="/stays" className="btn ghost">Change stay</Link>
                <button type="button" className="btn primary grow" onClick={() => setStep("travelers")}>Continue to traveler details →</button>
              </div>
            </>
          )}

          {step === "travelers" && (
            <form className="card pad bk-form" onSubmit={(e) => { e.preventDefault(); setStep("pay"); }}>
              <h1 className="h2">Who's traveling?</h1>
              <p className="bk-count">{req.travelers} traveler{req.travelers > 1 ? "s" : ""} on this booking · <button type="button" className="linkbtn" onClick={() => setTravelersOpen(true)}>add or remove travelers</button></p>
              {changeNote && <p className="notice">{changeNote}</p>}
              <p className="muted fine">Names as on each passport. These details stay on this device. In the demo they are never sent to our server.</p>
              <label className="field"><span>Lead traveler, full name</span>
                <input required autoComplete="name" maxLength={80} value={who.name} onChange={(e) => setWho({ ...who, name: e.target.value })} />
              </label>
              <label className="field"><span>Email for the confirmation</span>
                <input required type="email" autoComplete="email" maxLength={120} value={who.email} onChange={(e) => setWho({ ...who, email: e.target.value })} />
              </label>
              <label className="field"><span>Mobile (optional)</span>
                <input type="tel" autoComplete="tel" maxLength={30} value={who.phone} onChange={(e) => setWho({ ...who, phone: e.target.value })} />
              </label>
              {others.map((v, i) => (
                <label key={i} className="field"><span>Traveler {i + 2}, full name</span>
                  <input required maxLength={80} value={v} onChange={(e) => { const next = [...others]; next[i] = e.target.value; setWho({ ...who, others: next }); }} />
                </label>
              ))}
              <div className="bk-actions">
                <button type="button" className="btn ghost" onClick={() => setStep("review")}>← Back</button>
                <button className="btn primary grow">Continue to payment →</button>
              </div>
            </form>
          )}

          {step === "pay" && (
            <div className="card pad bk-pay">
              <h1 className="h2">Payment</h1>
              <div className="bk-total big"><span>To pay today</span><b>{money(total)}</b></div>
              <div className="pay-method">
                <span className="pay-card" aria-hidden="true">💳</span>
                <div>
                  <b>Secure card payment</b>
                  <p className="muted fine">In the live app you would pay on Stripe's hosted checkout page, and Wayfinder never sees your card number. This demo skips that page, so there's no card to enter and nothing is charged.</p>
                </div>
              </div>
              <label className="check">
                <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
                <span>I understand this is a demo. Nothing is reserved and I won't be charged.</span>
              </label>
              {error && <p className="error" role="alert">{error}</p>}
              <div className="bk-actions">
                <button type="button" className="btn ghost" onClick={() => setStep("travelers")} disabled={busy}>← Back</button>
                <button type="button" className="btn primary grow" disabled={!ack || busy} onClick={confirm}>
                  {busy ? "Booking…" : `Confirm demo booking · ${money(total)}`}
                </button>
              </div>
              {busy && (
                <ol className="bk-progress" aria-live="polite">
                  {PROGRESS.map((p, i) => (
                    <li key={p} className={i < progress ? "done" : i === progress ? "on" : ""}>
                      <span>{i < progress ? "✓" : i === progress ? <i className="spin" /> : "•"}</span>{p}
                    </li>
                  ))}
                </ol>
              )}
            </div>
          )}

          {step === "done" && booking && (
            <div className="bk-done">
              <div className={`card pad bk-confirm ${live ? "" : "cancelled"}`}>
                <motion.div className="bk-check" initial={{ scale: 0.4, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ type: "spring", stiffness: 260, damping: 16 }}>
                  {live ? "✓" : "✕"}
                </motion.div>
                <h1 className="h2">{live ? `You're going to ${to}!` : "Booking cancelled"}</h1>
                <p className="muted">{live ? "Your demo booking is confirmed." : `Cancelled ${new Date(booking.cancelled_at).toLocaleString()}. In the demo that means a full refund.`}</p>
                <button type="button" className="bk-ref" onClick={copyRef} title="Copy reference">
                  <small>Booking reference</small>
                  <b>{booking.reference}</b>
                  <span>{copied ? "Copied" : "Tap to copy"}</span>
                </button>
                {live && bookingChanged && <p className="notice">Your plan has changed since this booking. <button type="button" className="linkbtn" onClick={() => setStep("review")}>Review and book again</button></p>}
              </div>

              <div className="card pad bk-codes">
                <Line icon="✈️" title={`${booking.flight.airline || "Flights"} · ${from} ⇄ ${to}`} sub={`Airline reference (PNR) ${booking.flight.pnr}`} amount={money(booking.totals.flight)} />
                <Line icon="🏨" title={booking.stay.name} sub={`Hotel confirmation ${booking.stay.confirmation} · ${booking.totals.nights} nights`} amount={money(booking.totals.stay)} />
                {booking.tickets.map((t) => (
                  <Line key={t.code} icon="🎟️" title={t.name} sub={`Day ${t.day} · ${PART_LABEL[t.part]} · ticket ${t.code}`} />
                ))}
                {booking.free_activities.length > 0 && <p className="fine">Free, no ticket needed: {booking.free_activities.join(", ")}.</p>}
                <div className="bk-total"><span>{live ? "Paid (demo)" : "Refunded (demo)"}</span><b>{money(booking.totals.total)}</b></div>
                {booking.lead?.email && <p className="fine">In the live app, the confirmation would be emailed to {booking.lead.email}.</p>}
              </div>

              <div className="bk-actions wrap-row">
                {live && <button type="button" className="btn primary" onClick={calendar}>📅 Add to calendar</button>}
                <Link to="/trip" className="btn ghost">Trip overview</Link>
                <Link to="/trips" className="btn ghost">My trips</Link>
                {live ? <button type="button" className="linkbtn danger" onClick={cancel}>Cancel booking</button>
                  : <button type="button" className="btn primary" onClick={() => setStep("review")}>Book again</button>}
              </div>
              {error && <p className="error" role="alert">{error}</p>}
            </div>
          )}
        </motion.div>
      </AnimatePresence>

      <TravelersSheet open={travelersOpen} onClose={() => setTravelersOpen(false)} say={setChangeNote} />
      {step !== "done" && step !== "review" && (
        <details className="bk-mini card pad">
          <summary>Trip summary · <b>{money(total)}</b></summary>
          {summary}
        </details>
      )}
    </div>
  );
}
