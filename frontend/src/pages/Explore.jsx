import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Link, Navigate } from "react-router-dom";
import { Bar, BarChart, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useTrip } from "../state/TripContext.jsx";
import { KIND_META, TAG_LABEL } from "../lib/constants";
import { km, metres, money } from "../lib/format";
import MapView from "../components/MapView.jsx";
import Photo from "../components/Photo.jsx";
import BackLink from "../components/BackLink.jsx";

function Venue({ v }) {
  const meta = KIND_META[v.kind] || KIND_META.experience;
  const detail = [v.blurb, v.distance_m ? `${metres(v.distance_m)} away` : null, v.rating ? `★ ${v.rating}` : null].filter(Boolean).join(" · ");
  return (
    <li className="venue">
      <span className="kind" style={{ "--c": meta.color }}>{meta.label}</span>
      <div className="venue-main">
        <b>{v.website ? <a href={v.website} target="_blank" rel="noreferrer">{v.name}</a> : v.name}</b>
        <small>{detail}</small>
      </div>
      {v.price != null && (
        <div className="venue-price">
          <b>{money(v.price)}</b>
          {v.deal && <><s>{money(v.deal.typical_price)}</s><em className="badge deal sm">−{v.deal.pct}%</em></>}
        </div>
      )}
    </li>
  );
}

function SightCard({ item, n, selected, planned, travelers, onSelect, onToggle }) {
  const hasCost = item.cost != null;
  const demoDeals = item.nearby?.some((v) => v.deal);
  return (
    <motion.article
      layout
      className={`sight card ${selected ? "selected" : ""}`}
      onClick={() => onSelect(`s:${item.name}`)}
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.45 }}
    >
      <Photo k={item.photo} src={item.photo_url} info={item.photo_credit} alt={item.name} className="sight-photo" credit>
        {n != null && <span className="num">{n}</span>}
        {item.matches.length > 0 && <span className="badge gold match">★ Your pick</span>}
      </Photo>
      <div className="sight-body">
        <div className="sight-top">
          <div>
            <h3>{item.name}</h3>
            <p className="muted">
              {item.why}
              {item.url && <> · <a href={item.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>Wikipedia ↗</a></>}
            </p>
          </div>
        </div>
        <div className="facts-row">
          {item.duration && <span className="fpill">⏱ {item.duration}</span>}
          {hasCost && (
            <span className="fpill">{item.cost ? `≈ ${money(item.cost)} pp` : "Free"}{item.cost_note ? ` · ${item.cost_note}` : ""}</span>
          )}
          {item.matches.map((t) => <span key={t} className="tag hit">★ {TAG_LABEL[t] || t}</span>)}
        </div>
        {item.nearby?.length > 0 && (
          <div className="nearby">
            <span className="nearby-h">{demoDeals ? <>Nearby deals <em>demo</em></> : "Eat nearby"}</span>
            <ul>{item.nearby.map((v) => <Venue key={v.name} v={v} />)}</ul>
          </div>
        )}
        <button
          className={`btn ${planned ? "ghost" : "primary"} sm`}
          onClick={(e) => { e.stopPropagation(); onToggle(item); }}
        >
          {planned ? `✓ In your plan${hasCost ? ` · ${money(item.cost * travelers)}` : ""}` : "Add to my plan"}
        </button>
      </div>
    </motion.article>
  );
}

export default function Explore() {
  const ctx = useTrip();
  if (!ctx.trip) return <Navigate to="/" replace />;
  return <ExploreView {...ctx} />;
}

function ExploreView({ trip, planned, toggleItem, cityName }) {
  const { it, req } = trip;
  const g = it.guide;
  const [tab, setTab] = useState("all");
  const [selected, setSelected] = useState(null);
  const byType = g?.by_type || {};
  const typeKeys = Object.keys(byType);
  const [typeTab, setTypeTab] = useState(null);
  const activeType = typeTab && byType[typeTab] ? typeTab : typeKeys.find((k) => byType[k].places.length) || typeKeys[0];

  const all = useMemo(() => (g ? [...g.places, ...g.adventures] : []), [g]);
  const numbering = useMemo(() => {
    const located = all.filter((i) => i.lat != null);
    return new Map(located.map((i, idx) => [i.name, idx + 1]));
  }, [all]);
  const hasAdventures = !!g?.adventures?.length;
  const shown = tab === "places" ? g?.places : tab === "adventures" ? g?.adventures : all;

  const pins = useMemo(() => {
    if (!g) return [];
    const sights = all.filter((i) => i.lat != null).map((i) => ({ id: `s:${i.name}`, lat: i.lat, lng: i.lng, kind: "sight", label: String(numbering.get(i.name)), title: i.name, color: "#ffffff" }));
    const venues = (g.venues || []).map((v) => ({ id: `v:${v.name}`, lat: v.lat, lng: v.lng, kind: "venue", label: "", title: v.name, color: (KIND_META[v.kind] || KIND_META.experience).color }));
    const typed = (byType[activeType]?.places || []).map((p) => ({ id: `t:${p.id}`, lat: p.lat, lng: p.lng, kind: "venue", label: "", title: p.name, color: "#a78bfa" }));
    return [...typed, ...venues, ...sights];
  }, [g, all, numbering, byType, activeType]);

  const dealChart = useMemo(() => {
    if (!g) return [];
    return (g.venues || [])
      .filter((v) => v.deal)
      .map((v) => ({ name: v.name, price: v.price, saving: v.deal.typical_price - v.price, pct: v.deal.pct, typical: v.deal.typical_price }))
      .sort((a, b) => b.pct - a.pct)
      .slice(0, 8);
  }, [g]);

  const place = cityName(req.destination) !== req.destination ? cityName(req.destination) : g?.name || req.destination;
  const venueSel = selected?.startsWith("v:") ? g?.venues.find((v) => v.name === selected.slice(2)) : null;
  const totalSave = dealChart.reduce((s, d) => s + d.saving, 0);

  if (!g) {
    return (
      <div className="wrap page">
      <BackLink fallback="/" />
        <div className="page-head"><div><div className="eyebrow">Explore</div><h1 className="h2">Explore {place}</h1></div></div>
        <div className="card pad empty-state">
          <b>No destination guide for {req.destination}</b>
          <p className="muted">Your flights and stays are still ranked. Sights, weather and dining come from live sources for the 109 destinations in the list.</p>
          <Link to="/trip" className="btn primary">Back to your trip</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="wrap page">
      <BackLink fallback="/" />
      <div className="page-head">
        <div>
          <div className="eyebrow">Explore</div>
          <h1 className="h2">Things to do around {place}</h1>
          <p className="muted">
            {all.length} place{all.length === 1 ? "" : "s"} to see, ranked by your interests
            {g.venues?.length > 0 && <> · {g.venues.length} nearby restaurants{dealChart.length > 0 && `, ${dealChart.length} with a deal`}</>}.
          </p>
        </div>
        {hasAdventures && (
          <div className="tabs-inline" role="tablist">
            {[["all", "All"], ["places", "Places"], ["adventures", "Adventures"]].map(([k, label]) => (
              <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{label}</button>
            ))}
          </div>
        )}
      </div>

      {g.source === "live" && (
        <p className="fine src-note">
          {g.sources?.sights}. Photos from Wikimedia Commons, credited on each image. Restaurants from OpenStreetMap; free data has no
          restaurant prices or reviews, so none are shown.
        </p>
      )}

      <div className="explore-grid">
        <div className="sights">
          {shown.map((item) => (
            <SightCard
              key={item.name}
              item={item}
              n={numbering.get(item.name) ?? null}
              selected={selected === `s:${item.name}`}
              planned={planned.includes(item.name)}
              travelers={req.travelers}
              onSelect={setSelected}
              onToggle={toggleItem}
            />
          ))}
          {shown.length === 0 && <p className="muted">Nothing to show here yet.</p>}
        </div>

        {pins.length > 0 && (
          <aside className="map-col">
            <div className="card mapcard sticky">
              <MapView center={g.center} pins={pins} selectedId={selected} onSelect={setSelected} height={520} />
              <div className="map-legend">
                <span><i className="w" /> Sights</span>
                {g.venues?.length > 0 && Object.entries(KIND_META).filter(([k]) => g.venues.some((v) => v.kind === k)).map(([k, m]) => <span key={k}><i style={{ background: m.color }} /> {m.label}</span>)}
              </div>
              {venueSel && (
                <div className="venue-card">
                  <ul><Venue v={{ ...venueSel, distance_m: 0 }} /></ul>
                </div>
              )}
            </div>
          </aside>
        )}
      </div>

      {typeKeys.length > 0 && (
        <section className="card pad bytype">
          <div className="card-head">
            <div>
              <h2 className="card-title">Places you asked for</h2>
              <p className="muted">Real places from OpenStreetMap, notable ones first. Opening hours appear only when the map has them; free data has no ticket or drink prices.</p>
            </div>
          </div>
          <div className="chips">
            {typeKeys.map((k) => (
              <button key={k} className="chip" aria-pressed={k === activeType} onClick={() => setTypeTab(k)}>
                {byType[k].label} ({byType[k].places.length})
              </button>
            ))}
          </div>
          <ul className="type-list">
            {(byType[activeType]?.places || []).map((p) => (
              <li key={p.id}>
                <div>
                  <b>{p.name}</b>
                  <small>
                    {km(p.distance_to_center_km)} from the centre
                    {p.opening_hours && <> · <span title={p.opening_hours}>Hours: {p.opening_hours.length > 42 ? p.opening_hours.slice(0, 41) + "…" : p.opening_hours}</span></>}
                  </small>
                </div>
                <div className="links">
                  {p.website && <a href={p.website} target="_blank" rel="noreferrer">Website ↗</a>}
                  <a href={p.osm_url} target="_blank" rel="noreferrer">Map ↗</a>
                </div>
              </li>
            ))}
            {!(byType[activeType]?.places || []).length && <li className="muted">OpenStreetMap has none of this kind listed near the centre.</li>}
          </ul>
        </section>
      )}

      {dealChart.length > 0 && (
        <section className="card pad deals">
          <div className="card-head">
            <div>
              <h2 className="card-title">Best nearby deals</h2>
              <p className="muted">Biggest discounts among {g.venues.length} spots near the sights. Together they save {money(totalSave)} per person. <em className="demo-tag">Demo pricing</em></p>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={dealChart.length * 44 + 20}>
            <BarChart data={dealChart} layout="vertical" margin={{ top: 4, right: 96, left: 0, bottom: 0 }}>
              <XAxis type="number" domain={[0, 40]} tickLine={false} axisLine={false} tick={{ fill: "#8ea2b9", fontSize: 12 }} tickFormatter={(v) => `${v}%`} />
              <YAxis type="category" dataKey="name" width={170} tickLine={false} axisLine={false} tick={{ fill: "#c4d1e0", fontSize: 12 }} />
              <Tooltip
                cursor={{ fill: "rgba(255,255,255,.04)" }}
                formatter={(v, _n, p) => [`${v}% off · ${money(p.payload.price)} instead of ${money(p.payload.typical)}`, "Deal"]}
                contentStyle={{ background: "#0d1826", border: "1px solid #24364d", borderRadius: 10 }}
                itemStyle={{ color: "#e8eef6" }}
              />
              <Bar dataKey="pct" radius={[0, 8, 8, 0]} barSize={22} fill="#f5c76a">
                <LabelList dataKey="saving" position="right" formatter={(v) => `save ${money(v)}`} fill="#c4d1e0" fontSize={12} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="scale"><i className="gold" /> Discount versus the usual price, with the amount saved per person</div>
        </section>
      )}

      <div className="planbar glass">
        <div>
          <b>{trip.chosenItems.length} experience{trip.chosenItems.length === 1 ? "" : "s"} in your plan</b>
          <span className="muted">{trip.expCost ? ` · about ${money(trip.expCost)} for ${req.travelers} traveler${req.travelers > 1 ? "s" : ""}` : ""}</span>
        </div>
        <Link to="/trip" className="btn primary sm">View trip · {money(trip.total)}</Link>
      </div>
    </div>
  );
}
