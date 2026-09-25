import { Link, useNavigate } from "react-router-dom";
import { useTrip } from "../state/TripContext.jsx";
import { PART_ICON, PART_LABEL } from "../lib/dayplan";
import { distanceM, km } from "../lib/format";
import { careTasks, directionsUrl, nextUp, partStarts } from "../lib/tripday";
import { Thumb } from "./PlanSheets.jsx";

/** The card at the top of the trip that looks after you: before the trip, what's left to do; during it, what's
 * now and next, with directions; afterwards, a welcome home. Everything comes from the plan itself. */
export default function CareCard({ phase, place, onDay, onAdd }) {
  const { trip, booking, bookingChanged } = useTrip();
  const navigate = useNavigate();
  const { it, hotel, chosenItems } = trip;

  if (phase.phase === "before") {
    const tasks = careTasks({ phase, nights: it.nights, items: chosenItems, booking, bookingChanged, flight: trip.flight, hotel });
    const run = (a) => (a.kind === "book" ? navigate("/book") : onDay(a.day));
    const when = phase.daysToGo === 0 ? "today" : phase.daysToGo === 1 ? "tomorrow" : `in ${phase.daysToGo} days`;
    return (
      <section className="care card pad" aria-label="Your trip at a glance">
        <div className="care-head">
          <span className="care-pulse" aria-hidden="true" />
          <div>
            <b>{place} starts {when}</b>
            <span className="muted">{tasks.length ? "Here's what's left. We'll keep watching your plan." : "Everything's in place. We'll keep watching for deals along your route."}</span>
          </div>
        </div>
        {tasks.length > 0 && (
          <ul className="care-tasks">
            {tasks.map((t) => (
              <li key={t.key}>
                <span aria-hidden="true">{t.icon}</span>
                <span className="care-text">{t.text}</span>
                {t.action && <button type="button" className="btn ghost sm" onClick={() => run(t.action)}>{t.action.label}</button>}
              </li>
            ))}
          </ul>
        )}
      </section>
    );
  }

  if (phase.phase === "during") {
    const lastDay = phase.day > it.nights;
    const next = lastDay ? null : nextUp(chosenItems, phase.day, phase.part);
    const away = next && next.lat != null && hotel.lat != null ? distanceM(hotel, next) : null;
    return (
      <section className="care care-live card pad" aria-label="Now and next">
        <div className="care-head">
          <span className="care-pulse live" aria-hidden="true" />
          <div>
            <b>Day {phase.day} of {it.nights + 1} in {place} · {PART_ICON[phase.part]} {PART_LABEL[phase.part].toLowerCase()}</b>
            <span className="muted">{lastDay ? `Check out of ${hotel.name} and fly home today. Safe travels.` : "Here's what's next."}</span>
          </div>
        </div>
        {next ? (
          <div className="care-next">
            <Thumb item={next} className="care-thumb" />
            <div className="care-next-body">
              <small>Next · {partStarts(next.part)}</small>
              <b>{next.name}</b>
              <span className="muted">{[away != null && `${km(away / 1000)} from your stay`, next.duration].filter(Boolean).join(" · ")}</span>
            </div>
            {next.lat != null && <a className="btn primary sm" href={directionsUrl(next)} target="_blank" rel="noopener noreferrer">Directions ↗</a>}
          </div>
        ) : !lastDay && (
          <div className="care-next empty">
            <span>Nothing else planned for today.</span>
            <button type="button" className="btn ghost sm" onClick={() => onAdd(phase.day, phase.part)}>Find something</button>
            <Link to="/nearby" className="btn ghost sm">What's near me</Link>
          </div>
        )}
      </section>
    );
  }

  return (
    <section className="care card pad" aria-label="Welcome back">
      <div className="care-head">
        <span className="care-pulse done" aria-hidden="true" />
        <div>
          <b>Welcome home from {place}</b>
          <span className="muted">Your plan stays here in My trips. Ready for the next one?</span>
        </div>
      </div>
      <div className="care-actions">
        <Link to="/" className="btn primary sm">Plan another trip</Link>
        <Link to="/trips" className="btn ghost sm">My trips</Link>
      </div>
    </section>
  );
}
