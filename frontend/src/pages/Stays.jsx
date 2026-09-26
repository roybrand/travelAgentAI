import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Link, Navigate } from "react-router-dom";
import { Area, AreaChart, Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useTrip } from "../state/TripContext.jsx";
import { TAG_LABEL } from "../lib/constants";
import { km, money, metres } from "../lib/format";
import { PRICE_SOURCE, qualityLabel, qualityValue, stayPhotos } from "../lib/stay";
import MapView from "../components/MapView.jsx";
import Photo from "../components/Photo.jsx";
import SourceBadge from "../components/SourceBadge.jsx";
import BackLink from "../components/BackLink.jsx";

const SORTS = {
  best: ["Best match", (a, b) => b.score - a.score],
  price: ["Lowest price", (a, b) => a.price_per_night - b.price_per_night],
  rating: ["Highest rated", (a, b) => qualityValue(b) - qualityValue(a)],
  distance: ["Closest to centre", (a, b) => a.distance_to_center_km - b.distance_to_center_km],
};

function Meter({ label, value }) {
  return (
    <div className="rate-row">
      <span>{label}</span>
      <div className="rate-bar"><i style={{ width: `${(value / 5) * 100}%` }} /></div>
      <b>{value.toFixed(1)}</b>
    </div>
  );
}

function HotelCard({ h, best, selected, hovered, interests, nights, onSelect, onHover }) {
  const [shot, setShot] = useState(0);
  const photos = stayPhotos(h);
  const matched = interests.filter((t) => h.tags.includes(t));
  const gid = `g-${h.id}`;
  const quality = qualityLabel(h);
  const price = PRICE_SOURCE[h.price_source] || PRICE_SOURCE.demo;
  const sig = h.signals || {};
  // Skip amenities that just repeat an interest tag already shown ("Beachfront", "Nightlife nearby"...).
  const shownWords = matched.map((t) => (TAG_LABEL[t] || t).toLowerCase().split(" ")[0]);
  const amenities = (h.amenities || []).filter((a) => !shownWords.some((w) => a.toLowerCase().startsWith(w)));
  const facts = [
    sig.bars_300m != null && sig.bars_300m > 0 && `${sig.bars_300m} bars within 300 m`,
    sig.restaurants_300m > 0 && `${sig.restaurants_300m} restaurants within 300 m`,
    sig.beach_m != null && `Beach ${metres(sig.beach_m)} away`,
  ].filter(Boolean);

  return (
    <motion.article
      layout
      className={`hotel card ${selected ? "selected" : ""} ${hovered ? "hovered" : ""}`}
      onMouseEnter={() => onHover(h.id)}
      onMouseLeave={() => onHover(null)}
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <div className="gallery">
        <Photo k={photos[shot]} className="gallery-main" />
        <div className="badges">
          {best && <span className="badge gold">★ Agent's pick</span>}
          {h.deal && <span className="badge deal">−{h.deal.pct}%</span>}
        </div>
        <div className="thumbs">
          {photos.map((p, i) => (
            <button key={p} className={i === shot ? "on" : ""} onClick={() => setShot(i)} aria-label={`Photo ${i + 1}`}>
              <Photo k={p} />
            </button>
          ))}
        </div>
        <span className="illustrative">Illustrative photo</span>
      </div>

      <div className="hotel-body">
        <div className="hotel-top">
          <div>
            <h3>{h.name}</h3>
            <p className="muted">
              {[h.kind && h.kind[0].toUpperCase() + h.kind.slice(1), `${km(h.distance_to_center_km)} from the centre`, h.address, h.reviews && `${h.reviews.toLocaleString()} reviews`].filter(Boolean).join(" · ")}
            </p>
          </div>
          {quality && <div className="score-pill"><b>{quality}</b></div>}
        </div>

        <div className="price-row">
          <div>
            <span className="price">{money(h.price_per_night)}</span>
            <span className="muted"> / night</span>
            {h.deal && <s className="was">{money(h.deal.typical_price)}</s>}
          </div>
          <div className="stay-total">
            {money(h.price_per_night * nights)} for {nights} nights{" "}
            <SourceBadge mode={h.price_source === "amadeus" ? "amadeus" : h.price_source || "demo"} label={price.label} />
          </div>
        </div>
        {h.deal && (
          <div className="saving">
            Save {money((h.deal.typical_price - h.price_per_night) * nights)} versus the usual rate <em>demo pricing</em>
          </div>
        )}

        {h.price_history && (
          <div className="spark">
            <ResponsiveContainer width="100%" height={56}>
              <AreaChart data={h.price_history.map((v, i) => ({ i, v }))} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#2dd4bf" stopOpacity={0.45} />
                    <stop offset="100%" stopColor="#2dd4bf" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <YAxis hide domain={["dataMin - 8", "dataMax + 8"]} />
                <Area type="monotone" dataKey="v" stroke="#2dd4bf" strokeWidth={2} fill={`url(#${gid})`} dot={false} isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
            <span>Price over the last 30 days (demo)</span>
          </div>
        )}

        {h.rating_breakdown && (
          <div className="rates">
            {Object.entries(h.rating_breakdown).map(([k, v]) => <Meter key={k} label={k} value={v} />)}
          </div>
        )}

        {facts.length > 0 && (
          <ul className="facts-list">
            {facts.map((f) => <li key={f}>{f}</li>)}
          </ul>
        )}

        <div className="tags">
          {matched.map((t) => <span key={t} className="tag hit">★ {TAG_LABEL[t] || t}</span>)}
          {amenities.slice(0, 5).map((a) => <span key={a} className="tag">{a}</span>)}
        </div>

        {(h.website || h.osm_url) && (
          <div className="links">
            {h.website && <a href={h.website} target="_blank" rel="noreferrer">Hotel website ↗</a>}
            {h.osm_url && <a href={h.osm_url} target="_blank" rel="noreferrer">On OpenStreetMap ↗</a>}
          </div>
        )}

        <button className={`btn ${selected ? "ghost" : "primary"} full`} onClick={() => onSelect(h.id)} disabled={selected}>
          {selected ? "✓ Selected for your trip" : "Select this stay"}
        </button>
      </div>
    </motion.article>
  );
}

export default function Stays() {
  const { trip, hotelId, setHotelId, setHotelForSegment, cityName } = useTrip();
  if (!trip) return <Navigate to="/" replace />;
  return <StaysView trip={trip} hotelId={hotelId} setHotelId={setHotelId} setHotelForSegment={setHotelForSegment} cityName={cityName} />;
}

function StaysView({ trip, hotelId, setHotelId, setHotelForSegment, cityName }) {
  const [sort, setSort] = useState("best");
  const [dealsOnly, setDealsOnly] = useState(false);
  const [hover, setHover] = useState(null);
  const [segIndex, setSegIndex] = useState(0);

  const { it, req } = trip;
  const segments = trip.staySegments?.length ? trip.staySegments : [{ destination: req.destination, nights: it.nights, check_in: req.start_date, check_out: req.end_date, hotel: trip.hotel, hotel_options: it.hotel_options }];
  const segment = segments[Math.min(segIndex, segments.length - 1)];
  const options = segment.hotel_options || it.hotel_options;
  const selectedId = segment.selectedHotelId || (segment.primary ? hotelId : segment.hotel.id);
  const stats = {
    avg: Math.round(options.reduce((s, h) => s + h.price_per_night, 0) / options.length),
    min: Math.min(...options.map((h) => h.price_per_night)),
    max: Math.max(...options.map((h) => h.price_per_night)),
  };
  const bestId = segment.hotel.id;
  const anyDeals = options.some((h) => h.deal);
  const estimated = options.some((h) => h.price_source === "estimate");
  const chooseHotel = (id) => {
    if (setHotelForSegment) setHotelForSegment(segment.destination, id);
    else setHotelId(id);
  };

  const list = useMemo(() => {
    const filtered = dealsOnly ? options.filter((h) => h.deal) : options;
    return [...filtered].sort(SORTS[sort][1]);
  }, [options, sort, dealsOnly]);

  const located = useMemo(() => options.filter((h) => h.lat != null), [options]);
  const center = it.guide?.center || (located[0] && [located[0].lat, located[0].lng]);

  const chartData = useMemo(() => {
    const seen = {};
    return [...options]
      .sort((a, b) => a.price_per_night - b.price_per_night)
      .map((h) => {
        seen[h.name] = (seen[h.name] || 0) + 1;
        const name = h.name.length > 22 ? h.name.slice(0, 21) + "…" : h.name;
        return { id: h.id, label: seen[h.name] > 1 ? `${name} (${seen[h.name]})` : name, price: h.price_per_night, deal: !!h.deal };
      });
  }, [options]);

  const pins = useMemo(
    () => located.map((h) => ({ id: h.id, lat: h.lat, lng: h.lng, kind: "hotel", label: money(h.price_per_night), title: h.name, color: h.deal ? "#f5c76a" : "#2dd4bf" })),
    [located],
  );
  const cheapest = chartData[0];
  const below = options.filter((h) => h.price_per_night < stats.avg).length;

  return (
    <div className="wrap page">
      <BackLink fallback="/" />
      <div className="page-head">
        <div>
          <div className="eyebrow">Stays</div>
          <h1 className="h2">{options.length} places to stay in {cityName(segment.destination)}, compared</h1>
          <p className="muted">
            {segment.nights} night{segment.nights > 1 ? "s" : ""}, {segment.check_in} to {segment.check_out}. Average nightly rate here is <b>{money(stats.avg)}</b>{estimated && " (estimated)"}. {below} of {options.length} are below it.
            {cheapest && <> Cheapest: {cheapest.label} at {money(cheapest.price)}.</>}
          </p>
        </div>
        <div className="controls">
          <label className="select">
            <span>Sort by</span>
            <select value={sort} onChange={(e) => setSort(e.target.value)}>
              {Object.entries(SORTS).map(([k, [label]]) => <option key={k} value={k}>{label}</option>)}
            </select>
          </label>
          {anyDeals && <button className="chip" aria-pressed={dealsOnly} onClick={() => setDealsOnly((v) => !v)}>Deals only</button>}
        </div>
      </div>
      {segments.length > 1 && (
        <div className="segment-tabs" role="tablist" aria-label="Route stays">
          {segments.map((s, i) => (
            <button key={s.destination} type="button" className="chip" aria-pressed={i === segIndex} onClick={() => { setSegIndex(i); setHover(null); }}>
              {i + 1}. {cityName(s.destination)} · {s.nights} night{s.nights > 1 ? "s" : ""}
            </button>
          ))}
        </div>
      )}

      {estimated && (
        <div className="notice">
          <b>Real hotels, estimated prices.</b> Names, locations, star class and amenities come from OpenStreetMap. Nightly prices are
          modelled from star class, the city's price level and the season. Free data has no live hotel prices or guest reviews.
        </div>
      )}

      <div className="two-col even">
        <section className="card pad">
          <h2 className="card-title">Nightly price vs the area average</h2>
          <ResponsiveContainer width="100%" height={Math.max(230, chartData.length * 38 + 24)}>
            <BarChart data={chartData} layout="vertical" margin={{ top: 26, right: 28, left: 0, bottom: 0 }}>
              <XAxis type="number" tickLine={false} axisLine={false} tick={{ fill: "#8ea2b9", fontSize: 12 }} tickFormatter={(v) => `£${v}`} />
              <YAxis type="category" dataKey="label" width={140} tickLine={false} axisLine={false} tick={{ fill: "#c4d1e0", fontSize: 12 }} />
              <Tooltip cursor={{ fill: "rgba(255,255,255,.04)" }} formatter={(v) => [money(v), "Per night"]} contentStyle={{ background: "#0d1826", border: "1px solid #24364d", borderRadius: 10 }} itemStyle={{ color: "#e8eef6" }} />
              <ReferenceLine x={stats.avg} stroke="#f5c76a" strokeDasharray="5 4" label={{ value: `area avg ${money(stats.avg)}`, fill: "#f5c76a", fontSize: 12, position: "top", offset: 8 }} />
              <Bar dataKey="price" radius={[0, 8, 8, 0]} barSize={20}>
                {chartData.map((d) => <Cell key={d.id} fill={d.id === hotelId ? "#2dd4bf" : d.deal ? "#f5c76a" : "#4b6382"} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="scale"><i className="teal" /> Selected {anyDeals && <><i className="gold" /> Has a deal</>} <i className="slate" /> Standard rate</div>
        </section>

        <section className="card mapcard">
          {center && located.length > 0 ? (
            <MapView center={center} pins={pins} selectedId={selectedId} highlightId={hover} onSelect={chooseHotel} height={Math.max(300, chartData.length * 38 + 84)} />
          ) : (
            <div className="nomap"><b>No map for this destination</b><span>Hotel coordinates were not available.</span></div>
          )}
        </section>
      </div>

      <div className="hotels">
        {list.map((h) => (
          <HotelCard
            key={h.id}
            h={h}
            best={h.id === bestId}
            selected={h.id === selectedId}
            hovered={hover === h.id}
            interests={req.interests}
            nights={segment.nights}
            onSelect={chooseHotel}
            onHover={setHover}
          />
        ))}
        {list.length === 0 && <p className="muted">No deals in this search. Try again later.</p>}
      </div>

      <div className="cta-row">
        <Link to="/trip" className="btn primary">Back to your trip · {money(trip.total)}</Link>
        <Link to="/explore" className="btn ghost">Explore places and food</Link>
      </div>
    </div>
  );
}
