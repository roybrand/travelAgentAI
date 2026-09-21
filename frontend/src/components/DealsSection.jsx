import { useEffect, useState } from "react";
import { fetchEvents } from "../api";
import DealCard, { EventCard } from "./DealCard.jsx";

export const DISCLOSURE =
  "Partner deals are set by the businesses themselves. We review each one before it appears, but we do not guarantee price or availability. They are ranked by how well they match you, never by who pays.";

export function DealsGrid({ deals }) {
  return <div className="deal-grid">{deals.map((d) => <DealCard key={d.id} deal={d} />)}</div>;
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
