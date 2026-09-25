import { Link, useNavigate } from "react-router-dom";
import { useTrip } from "../state/TripContext.jsx";
import { PART_ICON, PART_LABEL } from "../lib/dayplan";
import { distanceM, km } from "../lib/format";
import { careTasks, dayDate, directionsUrl, nextUp, partStarts } from "../lib/tripday";
import { MOOD, MOODS } from "../lib/moods";
import { Thumb } from "./PlanSheets.jsx";

/** The card at the top of the trip that looks after you: before the trip, what's left to do; during it, what's
 * now and next, with directions; afterwards, a welcome home. Everything comes from the plan itself. */
const fmtDate = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short" });

/** Weather worth knowing before the trip: when the forecast arrives, or which days look wet. */
function weatherTasks(weather, req, nights) {
  if (!weather) return [];
  if (weather.reason === "too_far" && weather.ready_from) {
    return [{ key: "wx-later", icon: "🌤️", text: `The day-by-day forecast arrives on ${fmtDate(weather.ready_from)}, 16 days out` }];
  }
  const wet = Array.from({ length: nights + 1 }, (_, i) => i + 1).filter((d) => weather.days?.[dayDate(req.start_date, d)]?.wet);
  return wet.slice(0, 2).map((d) => ({ key: `wx-${d}`, icon: "🌧️", text: `Rain likely on Day ${d}. Indoor ideas come first`, action: { kind: "day", day: d, label: "See day" } }));
}

/** One line for changes to paid activities since booking. */
function ticketTask(c) {
  if (!c) return [];
  const bits = [c.added.length && `${c.added.length} new`, c.removed.length && `${c.removed.length} dropped`, c.moved.length && `${c.moved.length} moved`].filter(Boolean);
  return [{ key: "tickets", icon: "🎟️", text: `Paid activities changed since booking (${bits.join(", ")})`, action: { kind: "tickets", label: "Update" } }];
}

export default function CareCard({ phase, place, onDay, onAdd, weather, say, onTickets }) {
  const { trip, booking, bookingChanged, ticketChanges, moods, setMood } = useTrip();
  const navigate = useNavigate();
  const { it, hotel, chosenItems } = trip;

  if (phase.phase === "before") {
    const tasks = [...ticketTask(ticketChanges), ...careTasks({ phase, nights: it.nights, items: chosenItems, booking, bookingChanged, flight: trip.flight, hotel }), ...weatherTasks(weather, trip.req, it.nights)];
    const run = (a) => (a.kind === "book" ? navigate("/book") : a.kind === "tickets" ? onTickets?.() : onDay(a.day));
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
    const today = weather?.days?.[dayDate(trip.req.start_date, phase.day)];
    const mood = moods[phase.day];
    const pickMood = (k) => {
      setMood(phase.day, mood === k ? null : k);
      say?.(mood === k ? "Mood cleared" : `Feeling ${MOOD[k].label.toLowerCase()} today. Ideas and deals re-ordered`);
    };
    return (
      <section className="care care-live card pad" aria-label="Now and next">
        <div className="care-head">
          <span className="care-pulse live" aria-hidden="true" />
          <div>
            <b>Day {phase.day} of {it.nights + 1} in {place} · {PART_ICON[phase.part]} {PART_LABEL[phase.part].toLowerCase()}</b>
            <span className="muted">{lastDay ? `Check out of ${hotel.name} and fly home today. Safe travels.` : "Here's what's next."}{today ? ` ${today.icon} ${today.label}${today.tmax != null ? `, ${today.tmax}°` : ""}${today.wet ? ". Indoor ideas first" : ""}.` : ""}</span>
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
        {ticketChanges && (
          <div className="care-next empty">
            <span>🎟️ Paid activities changed since booking.</span>
            <button type="button" className="btn primary sm" onClick={onTickets}>Update tickets</button>
          </div>
        )}
        {!lastDay && (
          <div className="care-mood">
            <span>How do you feel today?</span>
            <div className="chips">
              {MOODS.map((m) => (
                <button key={m.key} type="button" className="chip" aria-pressed={mood === m.key} onClick={() => pickMood(m.key)}>{m.icon} {m.label}</button>
              ))}
            </div>
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
