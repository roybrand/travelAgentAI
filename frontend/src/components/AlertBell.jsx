import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAlerts } from "../state/AlertsContext.jsx";
import { useDealBooking } from "../state/DealBookingContext.jsx";
import AlertCard from "./AlertCard.jsx";
import { Avatar } from "./PersonCard.jsx";

/** The bell in the top bar. A badge counts what is new, and the panel shows the best few alerts right there. */
export function AlertBell() {
  const { alerts, unseen, markSeen, status } = useAlerts();
  const [open, setOpen] = useState(false);
  const n = unseen.length;
  const toggle = () => {
    if (open) markSeen(alerts.map((a) => a.id));
    setOpen(!open);
  };
  const top = alerts.slice(0, 4);
  return (
    <div className="bell-wrap">
      <button className={`bell ${n ? "ringing" : ""}`} onClick={toggle} aria-label={n ? `${n} new alerts` : "Alerts"} aria-expanded={open}>
        <span aria-hidden="true">🔔</span>
        {n > 0 && <b className="bell-badge">{n > 9 ? "9+" : n}</b>}
      </button>
      {open && (
        <>
          <div className="bell-scrim" onClick={toggle} />
          <div className="alert-panel" role="dialog" aria-label="Alerts">
            <header>
              <b>Your radar</b>
              <Link to="/alerts" onClick={toggle}>See everything →</Link>
              <button className="panel-close" onClick={toggle} aria-label="Close">×</button>
            </header>
            {top.length === 0 && <p className="muted pad">{status === "off" ? "Turn on alerts in Radar settings." : "Nothing hot right now. We will tell you the moment something matches."}</p>}
            <div className="alert-panel-list">{top.map((a) => <AlertCard key={a.id} a={a} compact />)}</div>
          </div>
        </>
      )}
    </div>
  );
}

/** Pop-ups that slide in when something new and good appears, wherever you are in the app. */
export function AlertToasts() {
  const { toasts, dismissToast, markSeen } = useAlerts();
  const booking = useDealBooking();
  // The business and moderator pages are workspaces: traveler pop-ups would sit over a check-in or a review.
  const { pathname } = useLocation();
  if (pathname.startsWith("/partners") || pathname.startsWith("/admin")) return null;
  return (
    <div className="alert-toasts" aria-live="polite">
      {toasts.map(({ id, alert: a }) => (
        <Link key={id} to={a.kind === "deal" ? "/alerts" : a.link} className={`alert-toast ${a.kind}`} onClick={() => { markSeen([a.id]); dismissToast(id); }}>
          <span className="toast-glow" aria-hidden="true" />
          {a.person ? <Avatar person={a.person} size={54} /> : <span className="toast-art" style={a.image ? { backgroundImage: `url(${a.image})` } : undefined}><em>{a.badge}</em></span>}
          <span className="toast-text">
            <small>{a.kind === "deal" ? "🔥 Hot deal for you" : a.kind === "message" ? "💬 New message" : a.kind === "request" ? "👋 Wants to meet you" : "✨ New match"}</small>
            <b>{a.title}</b>
            <span>{a.person ? a.body : a.reason.slice(0, 2).join(" · ") || a.body}</span>
            {a.kind === "deal" && a.deal && (
              <button type="button" className="toast-book" onClick={(e) => { e.preventDefault(); e.stopPropagation(); markSeen([a.id]); dismissToast(id); booking.open({ ...a.deal, title: a.deal.title || a.title }); }}>
                Book now
              </button>
            )}
          </span>
          <button className="toast-x" aria-label="Dismiss" onClick={(e) => { e.preventDefault(); e.stopPropagation(); dismissToast(id); }}>×</button>
        </Link>
      ))}
    </div>
  );
}
