import { useState } from "react";
import { Link } from "react-router-dom";
import { people, trackDealClick } from "../api";
import { usePeople } from "../state/PeopleContext.jsx";
import { useAlerts } from "../state/AlertsContext.jsx";
import PersonCard, { Avatar } from "./PersonCard.jsx";

const KIND = {
  deal: ["🔥", "Hot deal"], person: ["✨", "New match"], request: ["👋", "Wants to meet you"], message: ["💬", "New message"],
};

/** Prices are shown in the deal's own currency. */
const priceText = (n, cur) => new Intl.NumberFormat("en-GB", { style: "currency", currency: cur, maximumFractionDigits: 0 }).format(n);

function DealAlert({ a, compact }) {
  const d = a.deal;
  return (
    <article className={`alert-card deal ${a.hot ? "hot" : ""} ${compact ? "compact" : ""}`}>
      <div className="alert-art" style={a.image ? { backgroundImage: `url(${a.image})` } : undefined}>
        <span className="burst" aria-label={`Discount ${a.badge}`}>{a.badge}</span>
        {a.hours_left != null && <span className="countdown">⏱ {a.hours_left === 0 ? "Last hour" : `${a.hours_left}h left`}</span>}
      </div>
      <div className="alert-body">
        <span className="alert-kind">{a.hot ? "🔥 Hot deal" : "🏷️ Deal"} · {d.category_label} · {d.city}</span>
        <h3>{a.title}</h3>
        <p className="alert-price">
          <b>{priceText(d.price, d.currency)}</b>
          {d.reference_price && <s>{priceText(d.reference_price, d.currency)}</s>}
          <span>at {d.partner_name}</span>
        </p>
        <div className="alert-reasons">{a.reason.map((r) => <span key={r} className="tag hit">{r}</span>)}</div>
        <div className="alert-actions">
          <a className="btn primary sm" href={d.url} target="_blank" rel="noopener noreferrer sponsored" onClick={() => trackDealClick(d.id)}>Get this deal ↗</a>
          <Link className="btn ghost sm" to={a.link}>All deals here</Link>
        </div>
        {!compact && <p className="fine">Partner deal, set by the business and reviewed by us. Never ranked by who pays.</p>}
      </div>
    </article>
  );
}

function PersonAlert({ a, compact }) {
  const { token } = usePeople();
  const { refresh } = useAlerts();
  const [state, setState] = useState("");
  const [icon, label] = KIND[a.kind];
  const answer = async (accept) => {
    try {
      await people.respond(token, a.connection_id, accept);
      setState(accept ? "You are connected." : "Declined.");
      refresh();
    } catch (e) {
      setState(e.message);
    }
  };
  return (
    <article className={`alert-card person ${a.kind} ${compact ? "compact" : ""}`}>
      <div className="alert-person-head">
        <span className="alert-kind">{icon} {label}</span>
        <span className="burst small">{a.badge}</span>
      </div>
      <h3>{a.title}</h3>
      {compact ? (
        <div className="alert-person-mini"><Avatar person={a.person} size={44} /><p className="muted">{a.body}</p></div>
      ) : (
        <PersonCard person={a.person} showActions={a.kind === "person"} extra={<p className="quote">{a.body}</p>} />
      )}
      {a.reason?.length > 0 && !compact && <div className="alert-reasons">{a.reason.map((r) => <span key={r} className="tag hit">{r}</span>)}</div>}
      <div className="alert-actions">
        {a.kind === "request" && !state && (
          <>
            <button className="btn primary sm" onClick={() => answer(true)}>Accept and chat</button>
            <button className="btn ghost sm" onClick={() => answer(false)}>Not now</button>
          </>
        )}
        {a.kind === "message" && <Link className="btn primary sm" to={a.link}>Open chat</Link>}
        {a.kind === "person" && compact && <Link className="btn primary sm" to={a.link}>See profile</Link>}
        {a.kind === "request" && compact && !state && <Link className="btn ghost sm" to={a.link}>Open inbox</Link>}
        {state && (
          <p className="fine">
            {state} {state.startsWith("You are connected") && <Link to="/people?tab=inbox">Open Inbox →</Link>}
          </p>
        )}
      </div>
    </article>
  );
}

/** One alert, whatever its kind: a deal with a picture and a discount burst, or a person with their profile. */
export default function AlertCard({ a, compact = false }) {
  return a.kind === "deal" ? <DealAlert a={a} compact={compact} /> : <PersonAlert a={a} compact={compact} />;
}
