import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { fetchTonight, people } from "../api";
import { useTrip } from "../state/TripContext.jsx";
import { isoDate, longDate, metres, money } from "../lib/format";
import DestSelect from "../components/DestSelect.jsx";
import { EventCard, PartnerBadge } from "../components/DealCard.jsx";
import { DealsGrid } from "../components/DealsSection.jsx";
import Going from "../components/Going.jsx";
import MapView from "../components/MapView.jsx";
import Photo from "../components/Photo.jsx";
import BackLink from "../components/BackLink.jsx";

const KINDS = [["clubs", "🪩 Clubs"], ["bars", "🍸 Bars and pubs"]];
const ICON = { nightclub: "🪩", pub: "🍸" };

function addDays(n) {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return isoDate(d);
}

function Venue({ v, n, selected, onSelect, dest, day, count, onCount }) {
  const open = v.tonight.open;
  return (
    <motion.article
      layout
      className={`card rec venue ${selected ? "selected" : ""}`}
      onClick={() => onSelect(v.id)}
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(n, 8) * 0.04 }}
    >
      <Photo src={v.photo_url} info={v.photo_credit} alt={v.name} className="rec-photo" credit>
        <span className="num">{n + 1}</span>
        {!v.photo_url && <span className="rec-icon">{ICON[v.type] || "🌙"}</span>}
      </Photo>
      <div className="rec-body">
        <div className="deal-meta">
          <span className="fpill">{v.kind_label}</span>
          {open === true && <span className="src-badge ok">Open tonight {v.tonight.hours}</span>}
          {open == null && <span className="src-badge muted">Hours not listed</span>}
          {v.deal && <PartnerBadge />}
        </div>
        <h3>{v.name}</h3>
        <div className="facts-row">
          {v.why.filter((w) => !w.startsWith("Open tonight") && !w.startsWith("Opening hours not listed")).map((w) => <span key={w} className="tag">{w}</span>)}
        </div>

        {v.deal ? (
          <div className="venue-deal">
            <b>{v.deal.title}</b>
            <span className="deal-price"><b>{money(v.deal.price, v.deal.currency)}</b>{v.deal.reference_price && <s>{money(v.deal.reference_price, v.deal.currency)}</s>}{v.deal.price_note && <span>{v.deal.price_note}</span>}</span>
            <a className="btn primary sm" href={v.deal.url} target="_blank" rel="noopener noreferrer sponsored" onClick={(e) => e.stopPropagation()}>Get this deal ↗</a>
          </div>
        ) : (
          <p className="price-none">
            {v.price_note} <Link to="/partners" onClick={(e) => e.stopPropagation()}>Own it? Post tonight's price</Link>
          </p>
        )}

        <Going venue={v} dest={dest} day={day} count={count} onChange={onCount} />

        <div className="links">
          <a href={`https://www.google.com/maps/dir/?api=1&destination=${v.lat},${v.lng}`} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>Directions ↗</a>
          {v.website && <a href={v.website} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}>Website ↗</a>}
          <a href={v.osm_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>Map data ↗</a>
        </div>
      </div>
    </motion.article>
  );
}

export default function Tonight() {
  const { form, setForm, destinations, cityName, trip } = useTrip();
  const [dest, setDest] = useState(trip?.req.destination || form.destination);
  const [day, setDay] = useState(addDays(0));
  const [kinds, setKinds] = useState(["clubs", "bars"]);
  const [state, setState] = useState({ data: null, loading: true, error: "" });
  const [selected, setSelected] = useState(null);
  const [counts, setCounts] = useState({});

  useEffect(() => {
    if (!kinds.length) return undefined;
    let live = true;
    setState((s) => ({ ...s, loading: true, error: "" }));
    fetchTonight({ dest, date: day, kinds: kinds.join(",") })
      .then((data) => live && setState({ data, loading: false, error: "" }))
      .catch((e) => live && setState({ data: null, loading: false, error: e.message }));
    return () => {
      live = false;
    };
  }, [dest, day, kinds.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  const data = state.data;
  const loadCounts = () => {
    if (data?.venues?.length) people.counts(data.venues.map((v) => v.id), day).then((r) => setCounts(r.counts)).catch(() => {});
  };
  useEffect(loadCounts, [data, day]); // eslint-disable-line react-hooks/exhaustive-deps
  const toggleKind = (k) => setKinds((ks) => (ks.includes(k) ? (ks.length > 1 ? ks.filter((x) => x !== k) : ks) : [...ks, k]));
  const pins = useMemo(
    () => (data?.venues || []).map((v, i) => ({ id: v.id, lat: v.lat, lng: v.lng, kind: "sight", label: String(i + 1), title: v.name, color: "#c4b5fd" })),
    [data],
  );
  const dc = destinations.find((d) => d.code === dest);

  return (
    <div className="wrap page">
      <BackLink fallback="/" />
      <div className="page-head">
        <div>
          <div className="eyebrow">Tonight</div>
          <h1 className="h2">Where to go out in {cityName(dest)}, {day === addDays(0) ? "tonight" : longDate(day)}</h1>
          <p className="muted">Real clubs and bars that are open that night, with photos, hours and any live deal. Prices appear only when a venue or ticket seller has published one.</p>
        </div>
        <div className="tonight-controls">
          <label className="select">Destination
            <DestSelect value={dest} onChange={(c) => { setDest(c); setForm((f) => ({ ...f, destination: c })); }} destinations={destinations} />
          </label>
          <label className="select">Night
            <input type="date" value={day} min={addDays(0)} max={addDays(14)} onChange={(e) => e.target.value && setDay(e.target.value)} />
          </label>
        </div>
      </div>

      <div className="chips deal-filters">
        {KINDS.map(([k, l]) => <button key={k} className="chip" aria-pressed={kinds.includes(k)} onClick={() => toggleKind(k)}>{l}</button>)}
        <Link to="/nearby" state={{ from: "Tonight" }} className="chip">📍 Find places near me right now</Link>
      </div>

      {state.error && <p className="error" role="alert">{state.error}</p>}
      {state.loading && <p className="muted">Looking up venues, photos and deals… the first search for a city can take up to a minute.</p>}

      {data && !state.loading && (
        <>
          {data.deals.length > 0 && (
            <section className="tonight-block">
              <h2 className="card-title">Tonight's deals</h2>
              <DealsGrid deals={data.deals} />
            </section>
          )}

          {data.events.length > 0 && (
            <section className="tonight-block">
              <h2 className="card-title">Live events tonight</h2>
              <div className="deal-grid">{data.events.map((e) => <EventCard key={e.id} event={e} />)}</div>
              <p className="fine">Events by Ticketmaster. Prices and availability are theirs.</p>
            </section>
          )}

          <section className="tonight-block">
            <h2 className="card-title">Best places</h2>
            {data.venues.length === 0 && <p className="muted">No open venues found for this night.</p>}
            {data.venues.length > 0 && (
              <div className="explore-grid">
                <div className="sights">
                  {data.venues.map((v, i) => <Venue key={v.id} v={v} n={i} selected={selected === v.id} onSelect={setSelected} dest={dest} day={day} count={counts[v.id] || 0} onCount={loadCounts} />)}
                </div>
                {dc && (
                  <aside className="map-col">
                    <div className="card mapcard sticky"><MapView center={[dc.lat, dc.lng]} pins={pins} selectedId={selected} onSelect={setSelected} height={520} /></div>
                  </aside>
                )}
              </div>
            )}
            {data.closed_hidden > 0 && <p className="fine">{data.closed_hidden} venue{data.closed_hidden > 1 ? "s are" : " is"} hidden because their listed hours say they are closed that night.</p>}
          </section>

          {data.notes.map((n) => <p className="fine" key={n}>{n}</p>)}
          <p className="fine">{data.ranking_note}</p>
          {!data.events_enabled && <p className="fine">Live events and ticket prices appear here once a free Ticketmaster key is added to <code>backend/.env</code>.</p>}
        </>
      )}
    </div>
  );
}
