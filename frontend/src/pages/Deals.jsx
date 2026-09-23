import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { fetchDeals } from "../api";
import { useTrip } from "../state/TripContext.jsx";
import DestSelect from "../components/DestSelect.jsx";
import { DealsGrid, DISCLOSURE, EventsBlock, FeaturedStrip } from "../components/DealsSection.jsx";
import MapView from "../components/MapView.jsx";
import { CATEGORY_ICON } from "../components/DealCard.jsx";
import BackLink from "../components/BackLink.jsx";

const CATEGORIES = [
  ["hotel", "Stays"], ["restaurant", "Restaurants"], ["bar", "Bars and pubs"], ["party", "Parties and clubs"],
  ["tour", "Tours"], ["activity", "Activities"], ["spa", "Spas"], ["car_rental", "Car rental"], ["flight", "Flights"],
];

export default function Deals() {
  const { form, setForm, trip, destinations, config, profile } = useTrip();
  const [dest, setDest] = useState(trip?.req.destination || form.destination);
  const [category, setCategory] = useState("");
  const [forTrip, setForTrip] = useState(!!trip);
  const [state, setState] = useState({ deals: [], city: "", loading: true, error: "" });

  const tripDates = trip && trip.req.destination === dest && forTrip ? { start: trip.req.start_date, end: trip.req.end_date } : {};
  const interests = form.interests.join(",");
  const placeTypes = (profile?.place_types || []).join(",");

  useEffect(() => {
    let live = true;
    setState((s) => ({ ...s, loading: true, error: "" }));
    fetchDeals({ dest, category, interests, place_types: placeTypes, ...tripDates })
      .then((r) => live && setState({ deals: r.deals, city: r.city, loading: false, error: "" }))
      .catch((e) => live && setState({ deals: [], city: "", loading: false, error: e.message }));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dest, category, interests, placeTypes, tripDates.start, tripDates.end]);

  const pins = useMemo(
    () => state.deals.filter((d) => d.lat != null).map((d, i) => ({ id: String(d.id), lat: d.lat, lng: d.lng, kind: "sight", label: String(i + 1), title: d.title, color: "#f5c76a" })),
    [state.deals],
  );
  const center = useMemo(() => {
    const d = destinations.find((x) => x.code === dest);
    return d ? [d.lat, d.lng] : null;
  }, [destinations, dest]);

  return (
    <div className="wrap page">
      <BackLink fallback="/" />
      <div className="page-head">
        <div>
          <div className="eyebrow">Deals and events</div>
          <h1 className="h2">Offers from local businesses{state.city ? ` in ${state.city}` : ""}</h1>
          <p className="muted">Hotels, restaurants, bars, tours and more, posted by the businesses and reviewed by us. Live events appear here too when they are switched on.</p>
        </div>
        <label className="select">
          Destination
          <DestSelect value={dest} onChange={(c) => { setDest(c); setForm((f) => ({ ...f, destination: c })); }} destinations={destinations} />
        </label>
      </div>

      <FeaturedStrip dest={dest} />

      <div className="chips deal-filters">
        <button className="chip" aria-pressed={category === ""} onClick={() => setCategory("")}>All</button>
        {CATEGORIES.map(([k, l]) => (
          <button key={k} className="chip" aria-pressed={category === k} onClick={() => setCategory(k)}>{CATEGORY_ICON[k]} {l}</button>
        ))}
        {trip && trip.req.destination === dest && (
          <label className="chip-check"><input type="checkbox" checked={forTrip} onChange={(e) => setForTrip(e.target.checked)} /> Only for my trip dates</label>
        )}
      </div>

      {state.error && <p className="error">{state.error}</p>}
      {state.loading && <p className="muted">Loading deals…</p>}
      {!state.loading && !state.error && state.deals.length === 0 && (
        <div className="card pad empty">
          <b>No partner deals here yet.</b>
          <p className="muted">Businesses in {state.city || "this city"} can add offers for free. Are you one?</p>
          <Link to="/partners" className="btn primary sm">List your business</Link>
        </div>
      )}

      {state.deals.length > 0 && (
        <div className="explore-grid deals-layout">
          <DealsGrid deals={state.deals} />
          {center && (
            <aside className="map-col">
              <div className="card mapcard sticky"><MapView center={center} pins={pins} height={520} /></div>
            </aside>
          )}
        </div>
      )}
      <p className="fine">{DISCLOSURE}</p>

      {config.ticketmaster && (
        <section className="deals-events">
          <h2 className="card-title">What is on</h2>
          <EventsBlock dest={dest} start={tripDates.start} end={tripDates.end} enabled />
        </section>
      )}
      {!config.ticketmaster && (
        <p className="fine">Live events (concerts, shows, parties) appear here once a free Ticketmaster key is added to <code>backend/.env</code>.</p>
      )}
    </div>
  );
}
