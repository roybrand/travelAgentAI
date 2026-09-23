import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { fetchCheckin } from "../api";
import { Avatar } from "../components/PersonCard.jsx";

/** A "meet safely" plan, open to anyone with the link -- no sign-in needed. Meant to be shared with a friend
 * who isn't on Wayfinder, so they know where a traveler meant to be and with whom. */
export default function SafetyCheckin() {
  const { token } = useParams();
  const [view, setView] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchCheckin(token).then(setView).catch((e) => setError(e.message));
  }, [token]);

  if (error) {
    return (
      <div className="wrap page narrow">
        <div className="card pad empty"><b>Link not found</b><p className="muted">{error}</p></div>
      </div>
    );
  }
  if (!view) return <div className="wrap page narrow"><p className="muted">Loading…</p></div>;

  const when = new Date(view.meet_at);
  return (
    <div className="wrap page narrow">
      <div className="card pad checkin-view">
        <div className="eyebrow">Wayfinder · Meet safely</div>
        <h1 className="h2">{view.my_name}'s plan</h1>
        {view.revoked && <p className="notice">This check-in has ended. {view.my_name} marked it done, or it expired.</p>}
        {!view.revoked && view.expired && <p className="notice">This check-in has expired.</p>}
        {!view.revoked && !view.expired && (
          <div className="checkin-facts">
            <div className="checkin-row"><Avatar person={{ display_name: view.other_name, photo_url: view.other_photo_url }} size={48} /><span>Meeting <b>{view.other_name}</b></span></div>
            <div className="checkin-row">📍 <span>{view.place_text}</span></div>
            <div className="checkin-row">🕒 <span>{when.toLocaleString(undefined, { weekday: "long", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</span></div>
            {view.note && <div className="checkin-row">📝 <span>{view.note}</span></div>}
          </div>
        )}
        <p className="fine">{view.my_name} shared this with you so you know their plan. It has no exact location, email or phone number. If you are worried, try to reach them directly.</p>
        <Link to="/" className="btn ghost sm">What is Wayfinder?</Link>
      </div>
    </div>
  );
}
