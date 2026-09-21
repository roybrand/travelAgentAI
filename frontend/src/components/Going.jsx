import { useState } from "react";
import { Link } from "react-router-dom";
import { people } from "../api";
import { usePeople } from "../state/PeopleContext.jsx";
import PersonCard from "./PersonCard.jsx";

/** "I'm going" for a place and a day, and who else is going. Signed-out visitors see only the number. */
export default function Going({ venue, dest, day, count, onChange }) {
  const { token, plans, refresh } = usePeople();
  const [list, setList] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const mine = plans.find((p) => p.place_key === venue.id && p.day === day);
  const others = count - (mine ? 1 : 0);

  const toggle = async () => {
    setBusy(true);
    setError("");
    try {
      if (mine) await people.unattend(token, mine.id);
      else await people.attend(token, { place_key: venue.id, place_name: venue.name, place_type: venue.type, dest, lat: venue.lat, lng: venue.lng, day });
      await refresh();
      onChange?.();
      setList(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const show = async () => {
    if (list) return setList(null);
    try {
      setList((await people.attendees(token, venue.id, day)).people);
    } catch (e) {
      setError(e.message);
    }
  };

  if (!token) {
    return (
      <p className="going" onClick={(e) => e.stopPropagation()}>
        👥 {count > 0 ? `${count} going` : "Be the first to say you're going"} · <Link to="/people">Sign in to join</Link>
      </p>
    );
  }
  return (
    <div className="going" onClick={(e) => e.stopPropagation()}>
      <div className="going-row">
        <button className={`btn ${mine ? "ghost" : "primary"} sm`} onClick={toggle} disabled={busy}>{mine ? "✓ You're going · Cancel" : "👥 I'm going"}</button>
        {others > 0 && <button className="linkbtn" onClick={show}>{list ? "Hide" : `See who's going (${others})`}</button>}
        {others === 0 && <small className="muted">{mine ? "You are the first. Others who join will appear here." : "No one yet"}</small>}
      </div>
      {error && <p className="err">{error}</p>}
      {list && (list.length === 0 ? <p className="fine">Nobody else who can be shown.</p> : <div className="person-grid">{list.map((p) => <PersonCard key={p.id} person={p} compact />)}</div>)}
    </div>
  );
}
