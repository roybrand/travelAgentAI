import { useMemo } from "react";
import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { trackDealClick } from "../api";
import { useNearby } from "../state/NearbyContext.jsx";
import { PartnerBadge } from "../components/DealCard.jsx";
import { useTrip } from "../state/TripContext.jsx";
import { metres } from "../lib/format";
import MapView from "../components/MapView.jsx";
import Photo from "../components/Photo.jsx";

const STATUS_TEXT = {
  off: "Off. Nothing is requested from your device.",
  asking: "Waiting for your location. Please allow access in the browser prompt.",
  watching: "On. Recommendations update as you move, and when the weather or time of day changes.",
  denied: "Location access was blocked. Allow it in your browser's site settings, then try again.",
  unsupported: "This browser has no location support.",
  insecure: "Phones only share location over HTTPS. This works on localhost on a computer; to use it on a phone, open the app over HTTPS.",
  error: "Could not get recommendations just now. It will retry when you move.",
};

const KIND_ICON = { plan: "📌", sight: "🏛️", food: "🍽️", deal: "🏷️", event: "🎟️" };
const CAT_ICON = { cafe: "☕", bar: "🍸", pub: "🍺", restaurant: "🍽️", indoor: "🏛️", outdoor: "🌳", plan: "📌", party: "🎉", hotel: "🛏️", tour: "🧭", activity: "🎟️", spa: "💆", car_rental: "🚗", event: "🎟️" };

function weatherText(w) {
  if (!w) return null;
  const t = w.temp_c != null ? `${Math.round(w.temp_c)}°C` : "";
  const sky = w.raining ? "raining now" : w.rain_soon ? "rain likely soon" : "dry";
  return `${t} · ${sky}`.trim();
}

export default function Nearby() {
  const { prefs, savePrefs, status, position, data, busy, refresh, requestNotifications } = useNearby();
  const { trip } = useTrip();
  const recs = data?.recommendations || [];

  const pins = useMemo(() => {
    const out = recs.map((r, i) => ({ id: r.id, lat: r.lat, lng: r.lng, kind: "sight", label: String(i + 1), title: r.title, color: "#fff" }));
    if (position) out.push({ id: "you", lat: position.lat, lng: position.lng, kind: "you", label: "", title: "You are here", color: "#38bdf8" });
    return out;
  }, [recs, position]);

  return (
    <div className="wrap page">
      <div className="page-head">
        <div>
          <div className="eyebrow">Nearby now</div>
          <h1 className="h2">Suggestions that follow you around</h1>
          <p className="muted">Places to see, eat and drink right where you are, shaped by the weather, the time of day, what you like and your trip plan.</p>
        </div>
      </div>

      <section className="card pad consent">
        <div className="switch-row">
          <div>
            <b>Turn on live recommendations</b>
            <p className="muted">{STATUS_TEXT[status]}</p>
          </div>
          <label className="switch" aria-label="Live recommendations">
            <input type="checkbox" checked={prefs.enabled} onChange={(e) => savePrefs({ enabled: e.target.checked })} />
            <span />
          </label>
        </div>
        <div className="sub-switches">
          <label className={!trip ? "off" : ""}>
            <input type="checkbox" checked={prefs.usePlan && !!trip} disabled={!trip} onChange={(e) => savePrefs({ usePlan: e.target.checked })} />
            Use my trip plan {trip ? "" : "(plan a trip first)"}
          </label>
          <label>
            <input type="checkbox" checked={prefs.quiet} onChange={(e) => savePrefs({ quiet: e.target.checked })} />
            Quiet hours: no device notifications from 10 pm to 8 am
          </label>
          <label>
            <input
              type="checkbox"
              checked={prefs.notify}
              onChange={(e) => (e.target.checked ? requestNotifications() : savePrefs({ notify: false }))}
              disabled={!("Notification" in window)}
            />
            Notify me when something new is nearby
          </label>
        </div>
        <p className="fine">
          Privacy: your position is sent to our server only to look up places around you. It is not stored, and the runtime log records rule names and the nearest city, never coordinates. Partner deals and events are labelled and shown only when you are close. Device notifications are limited to 3 a day. They work while the app or its tab is open; true background push to a closed phone needs a push service, which is not built yet.
        </p>
      </section>

      {prefs.enabled && (
        <>
          <div className="chips context-chips">
            {data?.context?.city && <span className="chip static">📍 {data.context.city}</span>}
            {data?.context?.weather && <span className="chip static">🌤 {weatherText(data.context.weather)}</span>}
            {data?.context?.day_part && <span className="chip static">🕒 {data.context.day_part} time</span>}
            {position && <span className="chip static">± {Math.round(position.accuracy)} m</span>}
            <button className="chip" onClick={refresh} disabled={!position || busy}>{busy ? "Looking…" : "↻ Refresh now"}</button>
          </div>

          <div className="explore-grid">
            <div className="sights">
              {recs.map((r, i) => (
                <motion.article key={r.id} className="card rec" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
                  <Photo src={r.photo_url} info={r.photo_credit} alt={r.title} className="rec-photo" credit>
                    <span className="num">{i + 1}</span>
                    {!r.photo_url && <span className="rec-icon">{CAT_ICON[r.category] || KIND_ICON[r.kind]}</span>}
                  </Photo>
                  <div className="rec-body">
                    {r.kind === "deal" && <div><PartnerBadge /></div>}
                    <h3>{r.title}</h3>
                    {r.subtitle && <p className="muted">{r.subtitle}</p>}
                    <p className="rec-why">{r.reason}</p>
                    <div className="facts-row">
                      <span className="fpill">{metres(r.distance_m)} away</span>
                      {r.kind === "plan" && <span className="tag hit">★ In your plan</span>}
                      {r.kind === "deal" && r.discount_pct >= 10 && <span className="badge deal sm">−{r.discount_pct}%</span>}
                      {r.price != null && r.currency && (
                        <span className="fpill">{r.kind === "event" ? "from " : ""}{new Intl.NumberFormat("en-GB", { style: "currency", currency: r.currency, maximumFractionDigits: 2 }).format(r.price)}{r.price_note ? ` ${r.price_note}` : ""}</span>
                      )}
                    </div>
                    <div className="links">
                      <a href={`https://www.google.com/maps/dir/?api=1&destination=${r.lat},${r.lng}&travelmode=walking`} target="_blank" rel="noreferrer">Directions ↗</a>
                      {r.kind === "deal" && r.url && <a href={r.url} target="_blank" rel="noopener noreferrer sponsored" onClick={() => trackDealClick(r.deal_id)}>Get this deal ↗</a>}
                      {r.kind === "event" && r.url && <a href={r.url} target="_blank" rel="noopener noreferrer">Tickets on {r.attribution} ↗</a>}
                      {r.kind !== "deal" && r.kind !== "event" && r.url && <a href={r.url} target="_blank" rel="noreferrer">More info ↗</a>}
                    </div>
                  </div>
                </motion.article>
              ))}
              {!recs.length && status === "watching" && <p className="muted">Nothing notable within walking distance. Move a little and it will update.</p>}
              {data?.notes?.map((n) => <p className="fine" key={n}>{n}</p>)}
            </div>
            {position && (
              <aside className="map-col">
                <div className="card mapcard sticky">
                  <MapView center={[position.lat, position.lng]} pins={pins} height={480} />
                </div>
              </aside>
            )}
          </div>
        </>
      )}

      {!prefs.enabled && (
        <div className="cta-row">
          <Link to="/" className="btn ghost">Plan a trip instead</Link>
        </div>
      )}
    </div>
  );
}
