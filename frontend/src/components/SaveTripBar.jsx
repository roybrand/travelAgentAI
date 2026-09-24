import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTrip } from "../state/TripContext.jsx";
import { tripTitle } from "../lib/trips";

const timeOf = (iso) => new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });

/** Shows that the open trip (and its day plan) is saved to My trips, and lets the traveler name or rename it. */
export default function SaveTripBar() {
  const { trip, savedTrip, renameTrip, saveCurrentTrip, cityName, saveError } = useTrip();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [justSaved, setJustSaved] = useState(false);
  const onTripsPage = useLocation().pathname === "/trips";
  if (!trip) return null;

  const startEdit = () => {
    setDraft(savedTrip?.name || "");
    setEditing(true);
  };
  const submit = (e) => {
    e.preventDefault();
    if (savedTrip) renameTrip(savedTrip.id, draft);
    else saveCurrentTrip(draft);
    setEditing(false);
    setJustSaved(true);
    setTimeout(() => setJustSaved(false), 2500);
  };

  if (editing) {
    return (
      <form className="savebar glass" onSubmit={submit}>
        <input
          autoFocus
          maxLength={60}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Name this trip, e.g. Honeymoon"
          aria-label="Trip name"
        />
        <button type="submit" className="btn primary sm">💾 Save</button>
        <button type="button" className="linkbtn" onClick={() => setEditing(false)}>Cancel</button>
      </form>
    );
  }

  return (
    <div className={`savebar glass ${savedTrip ? "saved" : ""}`}>
      {savedTrip ? (
        <>
          <span className="savebar-state" title="Your stay and day plan are saved as you change them">
            {saveError ? "⚠️ Not saved" : justSaved ? "✓ Saved" : "✓ Saved to My trips"}
          </span>
          <b className="savebar-name">{tripTitle(savedTrip, cityName)}</b>
          {!saveError && <span className="muted savebar-time">day plan included · updated {timeOf(savedTrip.updatedAt)}</span>}
          <button className="btn ghost sm" onClick={startEdit}>{savedTrip.name ? "✎ Rename" : "✎ Name this trip"}</button>
          {onTripsPage ? <Link to="/trip" className="linkbtn">Open itinerary →</Link> : <Link to="/trips" className="linkbtn">My trips →</Link>}
        </>
      ) : (
        <>
          <span className="savebar-state">Not saved</span>
          <button className="btn primary sm" onClick={startEdit}>💾 Save trip and day plan</button>
        </>
      )}
    </div>
  );
}
