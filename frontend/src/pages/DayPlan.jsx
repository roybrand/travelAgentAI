import { useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { useTrip } from "../state/TripContext.jsx";
import { PARTS, PART_ICON, PART_LABEL } from "../lib/dayplan";
import { TAG_LABEL } from "../lib/constants";
import { PLACE_TYPE_LABEL } from "../lib/profile";
import { longDate, money } from "../lib/format";
import Photo from "../components/Photo.jsx";
import BackLink from "../components/BackLink.jsx";
import SaveTripBar from "../components/SaveTripBar.jsx";

const label = (t) => TAG_LABEL[t] || PLACE_TYPE_LABEL[t] || t;
const itemPhoto = (i) => ({ k: i.photo, src: i.photo_url, info: i.photo_credit });

function addDays(iso, n) {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

/** A scheduled item, on a day: its photo, why it's here, its tags, and controls to move or remove it. */
function PlannedCard({ item, nights, onMove, onRemove, travelers }) {
  return (
    <article className="plan-item">
      <Photo {...itemPhoto(item)} className="plan-item-photo" alt={item.name}>
        {!item.photo && !item.photo_url && <span className="rec-icon">{item.source === "adventure" ? "✨" : "📍"}</span>}
      </Photo>
      <div className="plan-item-body">
        <b>{item.name}</b>
        <p className="muted">{item.why}</p>
        <div className="facts-row">
          {item.matches?.map((t) => <span key={t} className="tag hit">★ {label(t)}</span>)}
          {item.cost != null && <span className="fpill">{item.cost ? `≈ ${money(item.cost * travelers)}` : "Free"}</span>}
          {item.url && <a href={item.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>More info ↗</a>}
        </div>
      </div>
      <div className="plan-item-move">
        <select aria-label={`Move ${item.name} to a day`} value={item.day} onChange={(e) => onMove(item.key, Number(e.target.value), item.part)}>
          {Array.from({ length: nights }, (_, i) => i + 1).map((d) => <option key={d} value={d}>Day {d}</option>)}
        </select>
        <select aria-label={`Move ${item.name} to a time of day`} value={item.part} onChange={(e) => onMove(item.key, item.day, e.target.value)}>
          {PARTS.map((p) => <option key={p} value={p}>{PART_LABEL[p]}</option>)}
        </select>
        <button className="linkbtn danger" onClick={() => onRemove(item)}>Remove</button>
      </div>
    </article>
  );
}

/** A not-yet-approved idea: one tap ("+ Add") is the approval — nothing lands on the plan without it. */
function SuggestionCard({ item, onAdd }) {
  return (
    <article className="suggest-card">
      <Photo {...itemPhoto(item)} className="suggest-photo" alt={item.name}>
        {!item.photo && !item.photo_url && <span className="rec-icon">{item.source === "adventure" ? "✨" : "📍"}</span>}
      </Photo>
      <div className="suggest-body">
        <b>{item.name}</b>
        <p className="muted">{item.why}</p>
        <div className="facts-row">{item.matches?.map((t) => <span key={t} className="tag hit">★ {label(t)}</span>)}</div>
      </div>
      <button className="btn primary sm" onClick={() => onAdd(item)}>+ Add</button>
    </article>
  );
}

export default function DayPlan() {
  const { trip, cityName, moveItem, toggleItem } = useTrip();
  const [openDay, setOpenDay] = useState(1);
  const [openPart, setOpenPart] = useState("morning");
  if (!trip) return <Navigate to="/" replace />;

  const { it, req, chosenItems, candidates } = trip;
  const place = cityName(req.destination) !== req.destination ? cityName(req.destination) : it.guide?.name || req.destination;
  const nights = it.nights;
  const days = Array.from({ length: nights }, (_, i) => i + 1);

  const scheduledKeys = useMemo(() => new Set(chosenItems.map((i) => i.key)), [chosenItems]);
  const byDay = useMemo(() => {
    const m = new Map(days.map((d) => [d, []]));
    chosenItems.forEach((i) => m.get(i.day)?.push(i));
    return m;
  }, [chosenItems]); // eslint-disable-line react-hooks/exhaustive-deps

  const groups = useMemo(() => {
    const unscheduled = candidates.filter((c) => !scheduledKeys.has(c.key));
    const hasMatch = (i) => i.matches?.length > 0;
    const rest = unscheduled.filter((i) => !hasMatch(i));
    const byType = new Map();
    rest.filter((i) => i.source === "place").forEach((i) => {
      if (!byType.has(i.type)) byType.set(i.type, { key: i.type, label: i.typeLabel, items: [] });
      byType.get(i.type).items.push(i);
    });
    return [
      { key: "recommended", label: "Matches what you like", items: unscheduled.filter(hasMatch) },
      { key: "sight", label: "Sights", items: rest.filter((i) => i.source === "sight") },
      { key: "adventure", label: "Adventures and nightlife", items: rest.filter((i) => i.source === "adventure") },
      ...byType.values(),
    ].filter((g) => g.items.length > 0);
  }, [candidates, scheduledKeys]);

  return (
    <div className="wrap page">
      <BackLink fallback="/trip" />
      <div className="page-head">
        <div>
          <div className="eyebrow">Day plan</div>
          <h1 className="h2">Plan each day in {place}</h1>
          <p className="muted">Nothing is added until you tap “+ Add”. Move anything between days or times of day, or remove it, at any time.</p>
        </div>
      </div>
      <SaveTripBar />

      <div className="chips day-jump">
        {days.map((d) => (
          <button key={d} className="chip" aria-pressed={openDay === d} onClick={() => setOpenDay(d)}>
            Day {d} · {byDay.get(d).length || "0"}
          </button>
        ))}
      </div>

      {days.map((d) => (
        <section key={d} className={`card pad plan-day ${openDay === d ? "" : "collapsed"}`}>
          <button className="plan-day-head" onClick={() => setOpenDay(openDay === d ? null : d)}>
            <h2 className="card-title">Day {d} · {longDate(addDays(req.start_date, d - 1))}</h2>
            <span className="muted">{byDay.get(d).length} planned {openDay === d ? "▲" : "▼"}</span>
          </button>
          {openDay === d && (
            <div className="plan-parts">
              {PARTS.map((part) => {
                const items = byDay.get(d).filter((i) => i.part === part);
                const active = openPart === part;
                return (
                  <div key={part} className={`plan-part ${active ? "active" : ""}`}>
                    <button className="plan-part-h" aria-pressed={active} onClick={() => setOpenPart(part)} title="New picks go here">
                      <span>{PART_ICON[part]} {PART_LABEL[part]}</span>
                      <span className="plan-part-n">{active ? "Adding here" : items.length || ""}</span>
                    </button>
                    {items.map((item) => (
                      <PlannedCard key={item.key} item={item} nights={nights} travelers={req.travelers} onMove={moveItem} onRemove={toggleItem} />
                    ))}
                    {!items.length && (
                      <button className="plan-part-empty" onClick={() => setOpenPart(part)}>
                        {active ? "Tap “+ Add” below to fill this slot" : "Nothing yet. Tap to add here"}
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>
      ))}

      <section className="plan-suggestions">
        <h2 className="card-title">More things to add</h2>
        <p className="muted fine">{openDay ? <>New picks go to <b>Day {openDay} · {PART_LABEL[openPart]}</b>. Tap a time of day above to change it.</> : "Open a day above first, and new picks will land there."}</p>
        {groups.length === 0 && <p className="muted">You have added everything the guide found. Nice and full.</p>}
        {groups.map((g) => (
          <div key={g.key} className="suggest-group">
            <span className="tag-strong">{g.label}</span>
            <div className="suggest-grid">
              {g.items.map((item) => <SuggestionCard key={item.key} item={item} onAdd={(i) => toggleItem(i, openDay && { day: openDay, part: openPart })} />)}
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}
