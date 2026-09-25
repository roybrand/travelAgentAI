import { useState } from "react";
import { useTrip } from "../state/TripContext.jsx";
import { duration, money } from "../lib/format";
import Sheet from "./Sheet.jsx";
import SourceBadge from "./SourceBadge.jsx";

const SORTS = [
  ["value", "Best value", (a, b) => (b.score ?? 0) - (a.score ?? 0)],
  ["price", "Cheapest", (a, b) => a.total_price - b.total_price],
  ["time", "Fastest", (a, b) => a.duration_minutes - b.duration_minutes],
  ["depart", "Earliest", (a, b) => (a.depart_time || "99").localeCompare(b.depart_time || "99")],
];

const hm = (m) => (m >= 60 ? `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m` : `${m}m`);

/** How the flight connects: direct, or its stops with where and how long each change is (when the airline data
 * says; estimated fares only know the number of stops). */
export function connectionText(f) {
  if (f.stops === 0) return "Direct";
  const stops = `${f.stops} stop${f.stops > 1 ? "s" : ""}`;
  if (!f.via?.length) return stops;
  return `${stops} · via ${f.via.map((v, i) => (f.layover_minutes?.[i] != null ? `${v} (${hm(f.layover_minutes[i])} change)` : v)).join(", ")}`;
}

/** An estimated fare has no airline yet: its "airline" is the fare shape ("Direct, flexible fare"). Say so. */
const isEstimate = (f) => f.price_source === "estimate";

/** Compare every flight found for the trip (airline, times, connections, duration, price and where the price comes
 * from) and choose one. The trip total, the itinerary and the booking all follow the choice. */
export default function FlightPicker({ open, onClose, say }) {
  const { trip, setFlightId } = useTrip();
  const [sort, setSort] = useState("value");
  const [directOnly, setDirectOnly] = useState(false);
  if (!trip) return null;
  const { flight: current, flights, req, it } = trip;
  const cmp = SORTS.find(([k]) => k === sort)[2];
  const list = flights.filter((f) => !directOnly || f.stops === 0).sort(cmp);
  const hasDirect = flights.some((f) => f.stops === 0);
  const anyEstimate = flights.some(isEstimate);

  const choose = (f) => {
    setFlightId(f.id);
    onClose();
    const diff = f.total_price - current.total_price;
    say?.(`Flight changed${diff ? `: ${money(Math.abs(diff))} ${diff < 0 ? "less" : "more"} for everyone` : ""}. The trip total is updated`);
  };

  return (
    <Sheet
      open={open}
      onClose={onClose}
      wide
      title="Choose your flight"
      subtitle={<span className="muted">{flights.length} return flights for {req.travelers} traveler{req.travelers > 1 ? "s" : ""} · prices are for everyone, both ways</span>}
    >
      <div className="chips sheet-filter">
        {SORTS.map(([k, label]) => (
          <button key={k} type="button" className="chip" aria-pressed={sort === k} onClick={() => setSort(k)}>{label}</button>
        ))}
        {hasDirect && <button type="button" className="chip" aria-pressed={directOnly} onClick={() => setDirectOnly(!directOnly)}>Direct only</button>}
      </div>
      <div className="flight-list">
        {list.map((f) => {
          const mine = f.id === current.id;
          const diff = f.total_price - current.total_price;
          return (
            <article key={f.id} className={`flight-row ${mine ? "mine" : ""}`}>
              <div className="flight-main">
                <div className="flight-top">
                  <b>{isEstimate(f) ? "Typical fare" : f.airline}</b>
                  {f.id === it.flight.id && <span className="tag">Agent's pick</span>}
                  {f.labels?.map((l) => <span key={l} className="tag hit">{l}</span>)}
                </div>
                <div className="flight-times">
                  {f.depart_time ? <span>{f.depart_time}{f.arrive_time ? ` → ${f.arrive_time}` : ""}</span> : <span className="muted">Times when booked</span>}
                  <span>{duration(f.duration_minutes)}</span>
                  <span className={f.stops === 0 ? "direct" : "stops"}>{connectionText(f)}</span>
                </div>
                {isEstimate(f) && <small className="muted">{f.airline}. The airline is known only once real offers are connected</small>}
              </div>
              <div className="flight-price">
                <b>{money(f.total_price)}</b>
                <small>{money(f.price_per_traveler)} pp</small>
                {!mine && diff !== 0 && <small className={diff < 0 ? "cheaper" : "dearer"}>{diff < 0 ? "−" : "+"}{money(Math.abs(diff))}</small>}
                <SourceBadge mode={f.price_source} />
              </div>
              {mine
                ? <span className="flight-mine">✓ Your flight</span>
                : <button type="button" className="btn primary sm flight-choose" onClick={() => choose(f)}>Choose</button>}
            </article>
          );
        })}
      </div>
      <p className="fine">
        Ranked by the same score the agent uses: 60% price, 40% flight time. {anyEstimate ? "Estimate prices are modelled from distance, season and how far ahead you book, not quoted; connect Amadeus for real airlines, times and connections." : "Times are for the way out; the return is on the same booking."}
      </p>
    </Sheet>
  );
}
