import { useState } from "react";
import { useTrip } from "../state/TripContext.jsx";
import { trackDealClick } from "../api";
import { PARTS, PART_ICON, PART_LABEL } from "../lib/dayplan";
import { duration, metres, money } from "../lib/format";
import { qualityLabel } from "../lib/stay";
import { dayDate, nextUp, slotSuggestion } from "../lib/tripday";
import { PlannedRow } from "./PlanSheets.jsx";
import { connectionText } from "./FlightPicker.jsx";
import { CATEGORY_ICON, PartnerBadge } from "./DealCard.jsx";
import MapView from "./MapView.jsx";
import { useDealBooking } from "../state/DealBookingContext.jsx";

const fmtDay = (iso, opts) => new Date(iso + "T00:00:00").toLocaleDateString("en-GB", opts);

/** A deal you booked (demo), in the time slot you chose. Tap it for the voucher, or to cancel. */
function BookedDealRow({ b, onOpen }) {
  return (
    <button type="button" className="planned-row booked-deal" onClick={() => onOpen(b)}>
      <span className="planned-thumb booked-icon" aria-hidden="true">{CATEGORY_ICON[b.deal.category] || "🏷️"}</span>
      <span className="planned-body">
        <b>{b.deal.title}</b>
        <small>✓ Booked · {b.quantity} × · {money(b.total, b.currency)} · {b.reference}</small>
      </span>
      <span className="planned-more" aria-label="Voucher and cancel">⋯</span>
    </button>
  );
}

/** A partner deal along the day's route, with "Book" (a demo booking into this day). Labelled, and in the order the
 * server ranked it (never by payment). */
function RouteDeal({ deal, booked, onBook }) {
  return (
    <div className="route-deal-wrap">
    <a className="route-deal" href={deal.url} target="_blank" rel="noopener noreferrer sponsored" onClick={() => deal.id && trackDealClick(deal.id)}>
      <span className="route-deal-icon" aria-hidden="true">{CATEGORY_ICON[deal.category] || "🏷️"}</span>
      <span className="route-deal-body">
        <b>{deal.title}</b>
        <small>{metres(deal.distance_m)} from {deal.near} · {deal.partner_name}</small>
      </span>
      <span className="route-deal-price">
        {deal.discount_pct >= 10 && <em>−{deal.discount_pct}%</em>}
        <b>{money(deal.price, deal.currency || "GBP")}</b>
      </span>
      <PartnerBadge />
    </a>
    {booked ? <span className="flight-mine">✓ Booked</span> : <button type="button" className="btn primary sm" onClick={() => onBook(deal)}>Book</button>}
    </div>
  );
}

function Anchor({ icon, title, sub, action }) {
  return (
    <li className="tl-slot anchor">
      <div className="tl-mark" aria-hidden="true">{icon}</div>
      <div className="tl-content">
        <div className="anchor-row">
          <div className="anchor-body"><b>{title}</b>{sub && <small>{sub}</small>}</div>
          {action && <button type="button" className="tl-add-sm" onClick={action.run}>{action.label}</button>}
        </div>
      </div>
    </li>
  );
}

/** The whole trip, day by day: flights and stay as anchors, each time of day with what's planned (tap to move or
 * remove) or, if it's free, one fitting idea to add in a tap. Under each day, partner deals along that day's route
 * and a map of its stops. This is the page the traveler lives in, before and during the trip. */
export default function TripTimeline({ phase, dealsByDay, eventsByDate, sheets, onChangeFlight }) {
  const { trip, cityName, tripId } = useTrip();
  const dealBooking = useDealBooking();
  const booked = dealBooking.forTrip(tripId);
  const bookedDealIds = new Set(booked.map((b) => b.deal.id));
  const [mapDay, setMapDay] = useState(null);
  const { it, req, hotel, chosenItems, candidates } = trip;
  const flight = trip.flight;
  const nights = it.nights;
  const scheduled = new Set(chosenItems.map((i) => i.key));
  const taken = new Set(); // one idea is suggested in one empty slot only
  const quality = qualityLabel(hotel);
  const knownCentre = it.guide?.center || (hotel.lat != null ? [hotel.lat, hotel.lng] : null);
  const live = phase.phase === "during";
  const next = live && phase.day <= nights ? nextUp(chosenItems, phase.day, phase.part) : null;

  /** A day's time slots as rows: planned items, a free slot with one fitting idea, or free slots merged into one. */
  const slotRows = (d, items, past) => {
    const rows = [];
    PARTS.forEach((p) => {
      const here = items.filter((x) => x.part === p);
      const deals = booked.filter((b) => b.day === d && b.part === p);
      if (here.length || deals.length) return rows.push({ kind: "filled", part: p, items: here, deals });
      const idea = past ? null : slotSuggestion(candidates, scheduled, taken, p, hotel);
      if (idea) return rows.push({ kind: "idea", part: p, idea });
      const prev = rows[rows.length - 1];
      if (prev?.kind === "free") prev.parts.push(p);
      else rows.push({ kind: "free", parts: [p] });
      return undefined;
    });
    return rows;
  };

  return (
    <div className="trip-days">
      {Array.from({ length: nights + 1 }, (_, i) => i + 1).map((d) => {
        const date = dayDate(req.start_date, d);
        const isToday = live && phase.day === d;
        const past = live && d < phase.day;
        const items = chosenItems.filter((x) => x.day === d);
        const deals = dealsByDay[d] || [];
        const events = eventsByDate[date] || [];
        const lastDay = d === nights + 1;
        const pins = [
          ...(hotel.lat != null ? [{ id: "hotel", kind: "hotel", label: "Stay", title: hotel.name, lat: hotel.lat, lng: hotel.lng, color: "#2dd4bf" }] : []),
          ...items.filter((x) => x.lat != null).map((x, n) => ({ id: x.key, kind: "sight", label: String(n + 1), title: x.name, lat: x.lat, lng: x.lng })),
          ...deals.map((x) => ({ id: `deal-${x.id}`, kind: "venue", title: x.title, lat: x.lat, lng: x.lng, color: "#f5c76a" })),
        ];
        return (
          <section key={d} id={`day-${d}`} className={`tday card pad ${isToday ? "today" : ""} ${past ? "past" : ""}`}>
            <header className="tday-head">
              <div className="tday-date">
                <b>Day {d}</b>
                <span>{fmtDay(date, { weekday: "long", day: "numeric", month: "short" })}</span>
                {isToday && <span className="tag hit">Today</span>}
                {lastDay && <span className="tag">Travel home</span>}
              </div>
              {pins.length > 1 && (
                <button type="button" className="chip" aria-pressed={mapDay === d} onClick={() => setMapDay(mapDay === d ? null : d)}>
                  🗺️ {mapDay === d ? "Hide map" : "Map"}
                </button>
              )}
            </header>

            {mapDay === d && (
              <div className="tday-map">
                <MapView center={knownCentre || [pins[0].lat, pins[0].lng]} pins={pins} height={260} />
                <p className="fine">Numbers follow the day's order. Gold dots are partner deals along the way.</p>
              </div>
            )}

            <ol className="timeline">
              {d === 1 && (
                <>
                  <Anchor icon="✈️" title={`Fly ${cityName(req.origin)} → ${cityName(req.destination)}`} sub={[flight.airline ? `${flight.airline} · ${connectionText(flight)}` : connectionText(flight), flight.duration_minutes && duration(flight.duration_minutes), flight.depart_time && `departs ${flight.depart_time}`].filter(Boolean).join(" · ")} action={trip.flights.length > 1 ? { label: "Change", run: onChangeFlight } : null} />
                  <Anchor icon="🏨" title={`Check in at ${hotel.name}`} sub={[quality, `${money(hotel.price_per_night)} a night`].filter(Boolean).join(" · ")} />
                </>
              )}
              {!lastDay && slotRows(d, items, past).map((row) => {
                if (row.kind === "filled") {
                  const p = row.part;
                  return (
                    <li key={p} className="tl-slot filled">
                      <div className="tl-mark" aria-hidden="true">{PART_ICON[p]}</div>
                      <div className="tl-content">
                        <div className="tl-head">
                          <span>{PART_LABEL[p]}</span>
                          <button type="button" className="tl-add-sm" onClick={() => sheets.openAdd(d, p)} aria-label={`Add more to Day ${d} ${PART_LABEL[p]}`}>+ Add</button>
                        </div>
                        {row.items.map((x) => (
                          <div key={x.key} className={next?.key === x.key ? "is-next" : ""}>
                            {next?.key === x.key && <span className="next-flag">Next</span>}
                            <PlannedRow item={x} onOpen={(i) => sheets.openWhen(i, "move")} />
                          </div>
                        ))}
                        {row.deals.map((b) => <BookedDealRow key={b.reference} b={b} onOpen={dealBooking.openBooking} />)}
                      </div>
                    </li>
                  );
                }
                if (row.kind === "idea") {
                  const { part: p, idea } = row;
                  return (
                    <li key={p} className="tl-slot empty">
                      <div className="tl-mark" aria-hidden="true">{PART_ICON[p]}</div>
                      <div className="tl-content">
                        <div className="free-row">
                          <span className="free-label">{PART_LABEL[p]} <em>free</em></span>
                          <button type="button" className="idea-chip" onClick={() => sheets.addNow(idea.item, { day: d, part: p })} title={idea.item.why}>
                            <span className="idea-plus">+</span>
                            <span className="idea-chip-text"><b>{idea.item.name}</b>{idea.away != null && <small>{metres(idea.away)} from your stay</small>}</span>
                          </button>
                          <button type="button" className="linkbtn" onClick={() => sheets.openAdd(d, p)}>Other ideas</button>
                        </div>
                      </div>
                    </li>
                  );
                }
                // consecutive free slots with nothing to suggest share one line
                return (
                  <li key={row.parts.join("-")} className="tl-slot empty">
                    <div className="tl-mark" aria-hidden="true">{PART_ICON[row.parts[0]]}</div>
                    <div className="tl-content">
                      <div className="free-row">
                        <span className="free-label">{row.parts.map((x) => PART_LABEL[x]).join(" · ")} <em>free</em></span>
                        {row.parts.map((x) => (
                          <button key={x} type="button" className="linkbtn" onClick={() => sheets.openAdd(d, x)}>+ {PART_LABEL[x]}</button>
                        ))}
                      </div>
                    </div>
                  </li>
                );
              })}
              {lastDay && (
                <>
                  {booked.filter((b) => b.day === d).map((b) => (
                    <li key={b.reference} className="tl-slot filled">
                      <div className="tl-mark" aria-hidden="true">{PART_ICON[b.part]}</div>
                      <div className="tl-content"><BookedDealRow b={b} onOpen={dealBooking.openBooking} /></div>
                    </li>
                  ))}
                  <Anchor icon="🧳" title={`Check out of ${hotel.name}`} />
                  <Anchor icon="✈️" title={`Fly home ${cityName(req.destination)} → ${cityName(req.origin)}`} sub={`Return on the same booking${flight.airline ? ` · ${flight.airline}` : ""}`} action={trip.flights.length > 1 ? { label: "Change", run: onChangeFlight } : null} />
                </>
              )}
            </ol>

            {(deals.length > 0 || events.length > 0) && (
              <div className="tday-extra">
                {deals.length > 0 && (
                  <>
                    <div className="tday-extra-h">🏷️ On your way {isToday ? "today" : "this day"}</div>
                    {deals.map((x) => <RouteDeal key={x.id} deal={x} booked={bookedDealIds.has(x.id)} onBook={dealBooking.open} />)}
                  </>
                )}
                {events.length > 0 && (
                  <>
                    <div className="tday-extra-h">🎟️ On that night</div>
                    {events.slice(0, 2).map((e) => (
                      <a key={e.id} className="route-deal" href={e.url} target="_blank" rel="noopener noreferrer">
                        <span className="route-deal-icon" aria-hidden="true">🎟️</span>
                        <span className="route-deal-body"><b>{e.title}</b><small>{[e.venue, e.time].filter(Boolean).join(" · ")}</small></span>
                        {e.price_min != null && <span className="route-deal-price"><b>from {money(e.price_min, e.currency || "GBP")}</b></span>}
                      </a>
                    ))}
                  </>
                )}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
