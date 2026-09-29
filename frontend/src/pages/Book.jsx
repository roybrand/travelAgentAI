import { useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { useTrip } from "../state/TripContext.jsx";
import { PART_LABEL } from "../lib/dayplan";
import { duration, longDate, money } from "../lib/format";
import { tripCalendar, downloadCalendar } from "../lib/ics";
import BackLink from "../components/BackLink.jsx";
import SourceBadge from "../components/SourceBadge.jsx";

const numericCost = (value) => (typeof value === "number" && Number.isFinite(value) ? value : 0);

function externalSearch(query) {
  return `https://www.google.com/search?${new URLSearchParams({ q: query }).toString()}`;
}

function sourceCopy(mode) {
  if (mode === "amadeus" || mode === "live") return "Live provider result";
  if (mode === "travelpayouts") return "Recent fare data, not a live quote";
  if (mode === "estimate") return "Estimated from free data, not a quote";
  return "Demo data for product testing";
}

function HandoffCard({ item, amount, badge, children }) {
  return (
    <article className="handoff-card">
      <div>
        <div className="handoff-card-top">
          <span className="tag-strong">{item.provider}</span>
          {badge}
        </div>
        <h2>{item.title}</h2>
        <p className="muted">{item.price_scope}</p>
        {children}
      </div>
      <div className="handoff-side">
        <b>{amount}</b>
        <a className="btn primary" href={item.url} target="_blank" rel="noopener noreferrer sponsored">
          Open provider
        </a>
        <span className="fine">Checkout happens off Wayfinder.</span>
      </div>
    </article>
  );
}

/** Trusted handoff, not owned checkout: flights and stays open with external sellers; local partner deals stay in app. */
export default function Book() {
  const { trip, cityName, routeName, saveCurrentTrip, savedTrip, booking, bookingChanged, ticketChanges, readback } = useTrip();
  const [saved, setSaved] = useState(false);

  if (!trip) return <Navigate to="/" replace />;

  const { it, req, hotel, flight, flightCost, stayCost, expCost, total, chosenItems } = trip;
  const route = req.destinations?.length ? req.destinations : [req.destination];
  const firstStop = route[0] || req.destination;
  const finalStop = route.at(-1) || req.destination;
  const originKnown = !readback || readback.said?.includes("origin") || readback.selected?.includes("origin");
  const from = originKnown ? cityName(req.origin) : "Departure city";
  const to = cityName(firstStop);
  const backFrom = cityName(finalStop);
  const nights = it.nights;
  const stops = flight.stops === 0 ? "Direct" : `${flight.stops} stop${flight.stops > 1 ? "s" : ""}`;
  const paid = chosenItems.filter((i) => numericCost(i.cost) > 0);
  const free = chosenItems.filter((i) => numericCost(i.cost) <= 0);
  const handoff = it.handoff || {};
  const flightHandoff = handoff.flight || {
    provider: "Airline or flight marketplace",
    title: `${from} to ${to}${backFrom !== to ? `, return from ${backFrom}` : ""}`,
    url: externalSearch(`${from} to ${to} return flights ${req.start_date} ${req.end_date}`),
    price_scope: "Confirm baggage, fare class, refund rules and schedule changes before paying.",
    source: flight.price_source,
  };
  const stayHandoff = handoff.stay || {
    provider: "Hotel site or lodging marketplace",
    title: hotel.name,
    url: hotel.website || externalSearch(`${hotel.name} ${to} hotel ${req.start_date} ${req.end_date}`),
    price_scope: `Confirm taxes, fees, cancellation and room type before paying.`,
    source: hotel.price_source,
  };
  const booked = booking && booking.status !== "cancelled";
  const sourceWarnings = [flightHandoff, stayHandoff].filter((x) => !["amadeus", "live"].includes(x.source));

  const save = () => {
    saveCurrentTrip();
    setSaved(true);
  };
  const calendar = () => downloadCalendar(
    tripCalendar({ reference: savedTrip?.id || "WAYFINDER", req, cityFrom: from, cityTo: to, hotel, flight, items: chosenItems, booking }),
    `wayfinder-${routeName(req, "-").toLowerCase().replace(/[^a-z0-9-]+/g, "-")}.ics`,
  );

  return (
    <div className="wrap page narrow book-page">
      <BackLink fallback="/trip" />
      <div className="handoff-hero">
        <span className="tag-strong">Trusted handoff</span>
        <h1 className="h2">Book with providers. Keep Wayfinder as your trip brain.</h1>
        <p className="muted">
          We keep the itinerary, sources, prices and local deals organized here. Flight and stay checkout opens with external sellers so they handle fares, rooms, refunds and support.
        </p>
      </div>

      <div className="bk-summary card pad">
        <div className="bk-trip">
          <div>
            <div className="eyebrow">{originKnown ? `${from} -> ${to}` : to}</div>
            <b>{longDate(req.start_date)} - {longDate(req.end_date)}</b>
            <div className="muted">{nights} night{nights > 1 ? "s" : ""} · {req.travelers} traveler{req.travelers > 1 ? "s" : ""} · {routeName(req)}</div>
          </div>
        </div>
        <div className="handoff-total">
          <span>Planner estimate</span>
          <b>{money(total)}</b>
          <em>{money(Math.round(total / req.travelers))} per person before provider fees or changes</em>
        </div>
        {sourceWarnings.length > 0 && (
          <p className="notice">Some prices are not live checkout quotes: {sourceWarnings.map((x) => `${x.provider}: ${sourceCopy(x.source)}`).join("; ")}.</p>
        )}
      </div>

      <div className="handoff-list">
        <HandoffCard item={flightHandoff} amount={money(flightCost)} badge={<SourceBadge mode={flightHandoff.source} />}>
          <p className="fine">{stops} · {duration(flight.duration_minutes)}{flight.depart_time ? ` · departs ${flight.depart_time}` : ""}. Shown for everyone, return trip.</p>
        </HandoffCard>

        <HandoffCard item={stayHandoff} amount={money(stayCost)} badge={<SourceBadge mode={stayHandoff.source} />}>
          <p className="fine">{nights} x {money(hotel.price_per_night)} nightly planner price. {hotel.address || hotel.distance_to_center_km != null ? `${hotel.address || `${hotel.distance_to_center_km} km from centre`}.` : ""}</p>
        </HandoffCard>

        <article className="handoff-card local">
          <div>
            <div className="handoff-card-top">
              <span className="tag-strong">Wayfinder local marketplace</span>
              <SourceBadge mode="live" label="Partner deals" />
            </div>
            <h2>Activities, deals, transfers and vouchers</h2>
            <p className="muted">This is the part Wayfinder can own first: reviewed partner offers around your actual route, ranked by fit and distance, never by who pays.</p>
            {paid.length > 0 ? (
              <div className="bk-acts">
                <div className="bk-acts-h">Paid items already on your plan</div>
                {paid.map((i) => (
                  <div key={i.key} className="bk-act">
                    <span>Day {i.day} · {PART_LABEL[i.part]}</span>
                    <b>{i.name}</b>
                    <em>{req.travelers} x {money(i.cost)}</em>
                  </div>
                ))}
                <div className="bk-act total"><span /><b>Activity estimate</b><em>{money(expCost)}</em></div>
              </div>
            ) : (
              <p className="fine">No paid local items on this itinerary yet. Add partner deals from the route timeline or the deals page.</p>
            )}
            {free.length > 0 && <p className="fine">Free ideas on your plan: {free.map((i) => i.name).join(", ")}.</p>}
          </div>
          <div className="handoff-side">
            <b>{money(expCost)}</b>
            <Link className="btn primary" to="/deals">Find local deals</Link>
            <span className="fine">Vouchers stay inside Wayfinder.</span>
          </div>
        </article>
      </div>

      <div className="handoff-actions card pad">
        <div>
          <b>Keep the itinerary alive</b>
          <p className="muted">Save it, add it to your calendar, then come back during the trip for weather-aware ideas and route deals.</p>
        </div>
        <div className="bk-actions">
          <button type="button" className="btn primary" onClick={save}>{saved || savedTrip ? "Saved" : "Save itinerary"}</button>
          <button type="button" className="btn ghost" onClick={calendar}>Add to calendar</button>
          <Link to="/trip" className="btn ghost">Back to itinerary</Link>
        </div>
        {booked && bookingChanged && <p className="notice">Your saved demo booking no longer matches this itinerary. Use the provider links above for flight and stay changes.</p>}
        {booked && ticketChanges && <p className="notice">Local paid activities changed since booking. Update those vouchers from the trip timeline.</p>}
      </div>
    </div>
  );
}
