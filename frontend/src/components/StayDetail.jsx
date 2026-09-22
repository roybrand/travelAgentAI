import { useState } from "react";
import { TAG_LABEL } from "../lib/constants";
import { km, metres, money } from "../lib/format";
import { PRICE_SOURCE, qualityLabel, stayPhotos } from "../lib/stay";
import MapView from "./MapView.jsx";
import Photo from "./Photo.jsx";
import SourceBadge from "./SourceBadge.jsx";

function Meter({ label, value }) {
  return (
    <div className="rate-row">
      <span>{label}</span>
      <div className="rate-bar"><i style={{ width: `${(value / 5) * 100}%` }} /></div>
      <b>{value.toFixed(1)}</b>
    </div>
  );
}

/** The chosen stay in full: photo previews, quality, price and location, for the trip overview. */
export default function StayDetail({ hotel: h, interests = [], nights }) {
  const [shot, setShot] = useState(0);
  const photos = stayPhotos(h);
  const matched = interests.filter((t) => h.tags?.includes(t));
  const quality = qualityLabel(h);
  const price = PRICE_SOURCE[h.price_source] || PRICE_SOURCE.demo;
  const sig = h.signals || {};
  const shownWords = matched.map((t) => (TAG_LABEL[t] || t).toLowerCase().split(" ")[0]);
  const amenities = (h.amenities || []).filter((a) => !shownWords.some((w) => a.toLowerCase().startsWith(w)));
  const facts = [
    sig.bars_300m > 0 && `${sig.bars_300m} bars within 300 m`,
    sig.restaurants_300m > 0 && `${sig.restaurants_300m} restaurants within 300 m`,
    sig.beach_m != null && `Beach ${metres(sig.beach_m)} away`,
  ].filter(Boolean);

  return (
    <div className="hotel card stay-detail">
      <div className="gallery">
        <Photo k={photos[shot]} className="gallery-main" />
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

        {h.rating_breakdown && (
          <div className="rates">
            {Object.entries(h.rating_breakdown).map(([k, v]) => <Meter key={k} label={k} value={v} />)}
          </div>
        )}

        {facts.length > 0 && <ul className="facts-list">{facts.map((f) => <li key={f}>{f}</li>)}</ul>}

        <div className="tags">
          {matched.map((t) => <span key={t} className="tag hit">★ {TAG_LABEL[t] || t}</span>)}
          {amenities.slice(0, 6).map((a) => <span key={a} className="tag">{a}</span>)}
        </div>

        {(h.website || h.osm_url) && (
          <div className="links">
            {h.website && <a href={h.website} target="_blank" rel="noreferrer">Hotel website ↗</a>}
            {h.osm_url && <a href={h.osm_url} target="_blank" rel="noreferrer">On OpenStreetMap ↗</a>}
          </div>
        )}
      </div>

      {h.lat != null && h.lng != null && (
        <div className="stay-map">
          <MapView
            center={[h.lat, h.lng]}
            pins={[{ id: h.id, lat: h.lat, lng: h.lng, kind: "hotel", label: money(h.price_per_night), title: h.name, color: "#2dd4bf" }]}
            height={220}
          />
        </div>
      )}
    </div>
  );
}
