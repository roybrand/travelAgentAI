import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTrip } from "../state/TripContext.jsx";
import { groupTrips, pickFlight, tripTitle } from "../lib/trips";
import { candidateItems, scheduledItems } from "../lib/dayplan";
import { money, shortDate } from "../lib/format";
import Photo from "../components/Photo.jsx";
import SaveTripBar from "../components/SaveTripBar.jsx";

/** The numbers a saved trip card shows, worked out the same way as the open trip's total. */
function summarize(t) {
  const it = t.result.itinerary;
  const req = t.result.request;
  const hotel = it.hotel_options?.find((h) => h.id === t.hotelId) || it.hotel;
  const planned = scheduledItems(candidateItems(it.guide), t.schedule || {});
  const total = pickFlight(it, t.flightId).total_price + hotel.price_per_night * it.nights + planned.reduce((s, i) => s + (i.cost || 0) * req.travelers, 0);
  return { it, req, hotel, planned: planned.length, total };
}

/** A two-step delete, so one stray tap never loses a trip. */
function DeleteButton({ label, onConfirm }) {
  const [asking, setAsking] = useState(false);
  if (!asking) return <button className="linkbtn danger" onClick={() => setAsking(true)}>{label}</button>;
  return (
    <span className="trips-confirm">
      <span className="muted">Delete for good?</span>
      <button className="linkbtn danger" onClick={onConfirm}>Yes, delete</button>
      <button className="linkbtn" onClick={() => setAsking(false)}>Keep</button>
    </span>
  );
}

/** Name or rename a saved trip right from its card. */
function RenameButton({ t, onRename }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  if (!editing) {
    return <button className="linkbtn" onClick={() => { setDraft(t.name || ""); setEditing(true); }}>{t.name ? "✎ Rename" : "✎ Name"}</button>;
  }
  return (
    <form className="trips-rename" onSubmit={(e) => { e.preventDefault(); onRename(draft); setEditing(false); }}>
      <input autoFocus maxLength={60} value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="e.g. Honeymoon" aria-label="Trip name" />
      <button type="submit" className="btn primary sm">💾 Save</button>
      <button type="button" className="linkbtn" onClick={() => setEditing(false)}>Cancel</button>
    </form>
  );
}

function TripCard({ t, open, onOpen, onDelete, onRename, today, cityName }) {
  const { it, req, hotel, planned, total } = summarize(t);
  const g = it.guide;
  const past = req.end_date < today;
  return (
    <article className={`trips-card ${open ? "open" : ""}`}>
      <button className="trips-card-main" onClick={onOpen} title="Open this trip">
        <Photo k={g?.hero} src={g?.hero_url} info={g?.hero_credit} className="trips-photo" alt="" />
        <div className="trips-body">
          {t.name && <b className="trips-name">{tripTitle(t, cityName)}</b>}
          <div className="trips-when">
            <b>{shortDate(req.start_date)} to {shortDate(req.end_date)}</b>
            {open ? <span className="tag hit">Open now</span> : <span className={`tag ${past ? "" : "hit"}`}>{past ? "Past" : "Upcoming"}</span>}
          </div>
          {t.booking && <span className={`tag trips-booked ${t.booking.status === "cancelled" ? "" : "booked"}`}>{t.booking.status === "cancelled" ? "Booking cancelled" : `✓ Booked (demo) · ${t.booking.reference}`}</span>}
          <span className="muted">
            {it.nights} nights · {req.travelers} {req.travelers === 1 ? "traveler" : "travelers"} · from {req.origin}
          </span>
          <span className="muted">🏨 {hotel.name}</span>
          <div className="facts-row">
            <span className="fpill">≈ {money(total)}</span>
            <span className="fpill">{planned ? `${planned} planned ${planned === 1 ? "activity" : "activities"}` : "No day plan yet"}</span>
          </div>
        </div>
      </button>
      <div className="trips-card-foot">
        <span className="fine muted">Saved {shortDate(t.savedAt.slice(0, 10))}</span>
        <span className="trips-actions">
          <RenameButton t={t} onRename={onRename} />
          <DeleteButton label="Delete" onConfirm={onDelete} />
        </span>
      </div>
    </article>
  );
}

export default function Trips() {
  const { savedTrips, tripId, openTrip, deleteTrips, renameTrip, cityName, saveError, trip } = useTrip();
  const navigate = useNavigate();
  const today = new Date().toISOString().slice(0, 10);
  const groups = useMemo(() => groupTrips(savedTrips, today), [savedTrips, today]);

  return (
    <div className="wrap page">
      <div className="page-head">
        <div>
          <div className="eyebrow">My trips</div>
          <h1 className="h2">Your saved trips</h1>
          <p className="muted">
            Every trip you plan is saved here, with its stay and day plan, until you delete it. They are kept in this browser only.
          </p>
        </div>
      </div>
      {saveError && <p className="error">{saveError}</p>}
      {trip && (
        <div className="trips-open">
          <span className="tag-strong">The trip you have open</span>
          <SaveTripBar />
        </div>
      )}

      {groups.length === 0 && (
        <div className="card pad">
          <p className="muted">No saved trips yet. Plan one and it will appear here.</p>
          <Link to="/" className="btn primary sm">Plan a trip</Link>
        </div>
      )}

      {groups.map((grp) => (
        <section key={grp.code} className="card pad trips-group">
          <div className="trips-group-head">
            <h2 className="card-title">📍 {cityName(grp.code)} <span className="muted">· {grp.trips.length} {grp.trips.length === 1 ? "trip" : "trips"}</span></h2>
            {grp.trips.length > 1 && <DeleteButton label={`Delete all ${grp.trips.length}`} onConfirm={() => deleteTrips(grp.trips.map((t) => t.id))} />}
          </div>
          <div className="trips-grid">
            {grp.trips.map((t) => (
              <TripCard
                key={t.id}
                t={t}
                today={today}
                cityName={cityName}
                open={t.id === tripId}
                onOpen={() => openTrip(t.id) && navigate("/trip")}
                onDelete={() => deleteTrips([t.id])}
                onRename={(name) => renameTrip(t.id, name)}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
