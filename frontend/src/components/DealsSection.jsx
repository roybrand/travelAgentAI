import { useEffect, useState } from "react";
import { fetchEvents, fetchFeaturedDeals } from "../api";
import DealCard, { EventCard } from "./DealCard.jsx";

export const DISCLOSURE =
  "Partner deals are set by the businesses themselves. We review each one before it appears, but we do not guarantee price or availability. They are ranked by how well they match you, never by who pays.";

export function DealsGrid({ deals }) {
  return <div className="deal-grid">{deals.map((d) => <DealCard key={d.id} deal={d} />)}</div>;
}

/** A business paid to appear here for a destination. Always its own labelled strip, above the payment-blind
 * ranked list -- never merged into it, and paying for this never moves anything in that list. */
export function FeaturedStrip({ dest }) {
  const [deals, setDeals] = useState([]);
  useEffect(() => {
    if (!dest) return undefined;
    let live = true;
    fetchFeaturedDeals(dest).then((r) => live && setDeals(r.deals)).catch(() => live && setDeals([]));
    return () => {
      live = false;
    };
  }, [dest]);
  if (deals.length === 0) return null;
  return (
    <section className="featured-strip">
      <h2 className="card-title">★ Featured this week</h2>
      <div className="deal-grid">{deals.map((d) => <DealCard key={d.id} deal={d} />)}</div>
      <p className="fine">These businesses paid for this placement. It is a separate strip and never changes how the deals below are ranked.</p>
    </section>
  );
}

/** Live events for a city and date range. Renders nothing unless the server has a Ticketmaster key. */
export function EventsBlock({ dest, start, end, enabled }) {
  const [state, setState] = useState({ events: [], error: "" });
  useEffect(() => {
    if (!enabled || !dest) return undefined;
    let live = true;
    fetchEvents({ dest, start, end })
      .then((r) => live && setState({ events: r.events, error: "" }))
      .catch((e) => live && setState({ events: [], error: e.message }));
    return () => {
      live = false;
    };
  }, [enabled, dest, start, end]);

  if (!enabled) return null;
  return (
    <>
      {state.error && <p className="fine">{state.error}</p>}
      {state.events.length > 0 && (
        <>
          <div className="deal-grid">{state.events.slice(0, 6).map((e) => <EventCard key={e.id} event={e} />)}</div>
          <p className="fine">Events by Ticketmaster. Dates, prices and availability are theirs.</p>
        </>
      )}
      {!state.error && state.events.length === 0 && <p className="muted">No events found for these dates.</p>}
    </>
  );
}
