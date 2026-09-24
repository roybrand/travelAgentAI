import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTrip } from "../state/TripContext.jsx";
import { PARTS, PART_ICON, PART_LABEL, guessPart } from "../lib/dayplan";
import { TAG_LABEL } from "../lib/constants";
import { PLACE_TYPE_LABEL } from "../lib/profile";
import { money } from "../lib/format";
import { dayDate } from "../lib/tripday";
import Photo from "./Photo.jsx";
import Sheet from "./Sheet.jsx";

const label = (t) => TAG_LABEL[t] || PLACE_TYPE_LABEL[t] || t;
const itemPhoto = (i) => ({ k: i.photo, src: i.photo_url, info: i.photo_credit });
const PART_HINT = { morning: "Good in the morning", afternoon: "Good in the afternoon", evening: "Good in the evening", night: "Good at night" };
export const slotName = (d, p) => `Day ${d} · ${PART_LABEL[p]}`;
export const costText = (i) => (i.cost == null ? null : i.cost ? `≈ ${money(i.cost)} pp` : "Free");
const dayLabel = (start, d, opts) => new Date(dayDate(start, d) + "T00:00:00").toLocaleDateString("en-GB", opts);

export function Thumb({ item, className }) {
  return (
    <Photo {...itemPhoto(item)} className={className} alt={item.name}>
      {!item.photo && !item.photo_url && <span className="rec-icon">{item.source === "adventure" ? "✨" : "📍"}</span>}
    </Photo>
  );
}

/** Ideas not yet on the plan, in the groups used everywhere: what matches you, sights, adventures, then each
 * kind of real place the traveler asked for. */
export function ideaGroups(candidates, scheduledKeys) {
  const open = candidates.filter((c) => !scheduledKeys.has(c.key));
  const hasMatch = (i) => i.matches?.length > 0;
  const rest = open.filter((i) => !hasMatch(i));
  const byType = new Map();
  rest.filter((i) => i.source === "place").forEach((i) => {
    if (!byType.has(i.type)) byType.set(i.type, { key: i.type, label: i.typeLabel, items: [] });
    byType.get(i.type).items.push(i);
  });
  return [
    { key: "recommended", label: "Matches what you like", items: open.filter(hasMatch) },
    { key: "sight", label: "Sights", items: rest.filter((i) => i.source === "sight") },
    { key: "adventure", label: "Adventures and nightlife", items: rest.filter((i) => i.source === "adventure") },
    ...byType.values(),
  ].filter((g) => g.items.length > 0);
}

/** Day and time-of-day chips: the one way to say "when" everywhere (adding, moving). */
function SlotPicker({ nights, start, day, part, onDay, onPart, counts, suggested }) {
  return (
    <div className="slot-picker">
      <div className="slot-label">Day</div>
      <div className="slot-days">
        {Array.from({ length: nights }, (_, i) => i + 1).map((d) => (
          <button key={d} type="button" className="slot-day" aria-pressed={day === d} onClick={() => onDay(d)}>
            <b>Day {d}</b>
            <span>{dayLabel(start, d, { weekday: "short", day: "numeric" })}</span>
            {counts[d] > 0 && <i>{counts[d]}</i>}
          </button>
        ))}
      </div>
      <div className="slot-label">Time of day</div>
      <div className="slot-parts">
        {PARTS.map((p) => (
          <button key={p} type="button" className="slot-part" aria-pressed={part === p} onClick={() => onPart(p)}>
            <span aria-hidden="true">{PART_ICON[p]}</span> {PART_LABEL[p]}
            {suggested === p && <small>best fit</small>}
          </button>
        ))}
      </div>
    </div>
  );
}

/** A planned item: tap it to move it or take it off the plan. */
export function PlannedRow({ item, onOpen, extra }) {
  return (
    <button type="button" className="planned-row" onClick={() => onOpen(item)}>
      <Thumb item={item} className="planned-thumb" />
      <span className="planned-body">
        <b>{item.name}</b>
        <small>{extra || [costText(item), item.duration].filter(Boolean).join(" · ") || item.why}</small>
      </span>
      <span className="planned-more" aria-label={`Move or remove ${item.name}`}>⋯</span>
    </button>
  );
}

/** An idea row, used in the ideas list and inside the "add to this slot" sheet. */
export function IdeaRow({ item, hint, added, onAdd, onUndo, addLabel = "+ Add" }) {
  return (
    <article className={`idea-row ${added ? "added" : ""}`}>
      <Thumb item={item} className="idea-thumb" />
      <div className="idea-body">
        <b>{item.name}</b>
        <p className="muted">{item.why}</p>
        <div className="facts-row">
          {hint && <span className="tag fit">{hint}</span>}
          {item.matches?.slice(0, 2).map((t) => <span key={t} className="tag hit">★ {label(t)}</span>)}
          {costText(item) && <span className="fpill">{costText(item)}</span>}
        </div>
      </div>
      {added
        ? <button type="button" className="btn ghost sm idea-btn done" onClick={onUndo}>✓ Added<small>Undo</small></button>
        : <button type="button" className="btn primary sm idea-btn" onClick={onAdd}>{addLabel}</button>}
    </article>
  );
}

/** Everything needed to change the plan in place: the "add to this slot" sheet, the "when?" / move sheet and a
 * confirmation toast. Returns the openers and the UI to render once on the page. */
export function usePlanSheets({ onShowDay } = {}) {
  const { trip, toggleItem, moveItem } = useTrip();
  const [addSlot, setAddSlot] = useState(null); // { day, part } while the "add to this slot" sheet is open
  const [addedHere, setAddedHere] = useState([]); // keys added in the open sheet, so they stay visible with Undo
  const [filter, setFilter] = useState("fit");
  const [when, setWhen] = useState(null); // { item, day, part, mode: "add" | "move" }
  const [toast, setToast] = useState(null);
  const timer = useRef(null);

  const say = useCallback((msg, action) => {
    clearTimeout(timer.current);
    setToast({ msg, action });
    timer.current = setTimeout(() => setToast(null), 3400);
  }, []);
  useEffect(() => () => clearTimeout(timer.current), []);

  const chosenItems = trip?.chosenItems || [];
  const candidates = trip?.candidates || [];
  const scheduledKeys = useMemo(() => new Set(chosenItems.map((i) => i.key)), [chosenItems]);
  const counts = useMemo(() => chosenItems.reduce((m, i) => ({ ...m, [i.day]: (m[i.day] || 0) + 1 }), {}), [chosenItems]);
  const groups = useMemo(() => ideaGroups(candidates, scheduledKeys), [candidates, scheduledKeys]);

  const openAdd = useCallback((day, part) => {
    setAddSlot({ day, part });
    setAddedHere([]);
    setFilter("fit");
  }, []);
  const openWhen = useCallback((item, mode, defaultDay = 1) => {
    setWhen({ item, mode, day: mode === "move" ? item.day : defaultDay, part: mode === "move" ? item.part : guessPart(item) });
  }, []);
  /** Add straight into a slot (an inline suggestion), with Undo. */
  const addNow = useCallback((item, slot) => {
    toggleItem(item, slot);
    say(`Added ${item.name} to ${slotName(slot.day, slot.part)}`, { label: "Undo", run: () => toggleItem(item) });
  }, [toggleItem, say]);

  if (!trip) return { openAdd, openWhen, addNow, say, groups, ui: null };
  const { req, it } = trip;
  const nights = it.nights;

  const sheetIdeas = (() => {
    if (!addSlot) return [];
    const pool = candidates.filter((c) => !scheduledKeys.has(c.key) || addedHere.includes(c.key));
    const matched = (i) => i.matches?.length > 0;
    const inFilter = (i) => {
      if (filter === "fit") return true;
      if (filter === "recommended") return matched(i);
      if (filter === "sight" || filter === "adventure") return !matched(i) && i.source === filter;
      return !matched(i) && i.source === "place" && i.type === filter;
    };
    const score = (i) => (guessPart(i) === addSlot.part ? 2 : 0) + (matched(i) ? 1 : 0);
    return pool.filter(inFilter).sort((a, b) => score(b) - score(a));
  })();

  const closeAdd = () => {
    if (addedHere.length) say(`${addedHere.length} added to ${slotName(addSlot.day, addSlot.part)}`);
    setAddSlot(null);
  };
  const confirmWhen = () => {
    const { item, mode, day: d, part: p } = when;
    if (mode === "move") moveItem(item.key, d, p);
    else toggleItem(item, { day: d, part: p });
    setWhen(null);
    say(`${mode === "move" ? "Moved" : "Added"} to ${slotName(d, p)}`, onShowDay ? { label: `Show Day ${d}`, run: () => onShowDay(d) } : null);
  };
  const removeFromWhen = () => {
    const { item } = when;
    toggleItem(item);
    setWhen(null);
    say(`Removed ${item.name}`, { label: "Undo", run: () => toggleItem(item, { day: item.day, part: item.part }) });
  };

  const ui = (
    <>
      {toast && createPortal(
        <div className="plan-toast" role="status">
          <span>{toast.msg}</span>
          {toast.action && <button type="button" className="linkbtn" onClick={() => { toast.action.run(); setToast(null); }}>{toast.action.label}</button>}
        </div>,
        document.body,
      )}

      <Sheet
        open={!!addSlot}
        onClose={closeAdd}
        wide
        title={addSlot ? `Add to ${slotName(addSlot.day, addSlot.part)}` : ""}
        subtitle={addSlot && (
          <div className="chips sheet-parts">
            {PARTS.map((p) => (
              <button key={p} type="button" className="chip" aria-pressed={addSlot.part === p} onClick={() => setAddSlot({ ...addSlot, part: p })}>
                {PART_ICON[p]} {PART_LABEL[p]}
              </button>
            ))}
          </div>
        )}
        footer={<button type="button" className="btn primary full" onClick={closeAdd}>{addedHere.length ? `Done · ${addedHere.length} added` : "Done"}</button>}
      >
        {addSlot && (
          <>
            <div className="chips sheet-filter">
              <button type="button" className="chip" aria-pressed={filter === "fit"} onClick={() => setFilter("fit")}>Best fits first</button>
              {groups.map((g) => (
                <button key={g.key} type="button" className="chip" aria-pressed={filter === g.key} onClick={() => setFilter(g.key)}>{g.label}</button>
              ))}
            </div>
            {sheetIdeas.length === 0 && <p className="muted">Nothing left to add here. Try another group.</p>}
            <div className="idea-list">
              {sheetIdeas.map((item) => (
                <IdeaRow
                  key={item.key}
                  item={item}
                  hint={guessPart(item) === addSlot.part ? PART_HINT[addSlot.part] : null}
                  added={addedHere.includes(item.key)}
                  onAdd={() => { toggleItem(item, addSlot); setAddedHere((k) => [...k, item.key]); }}
                  onUndo={() => { toggleItem(item); setAddedHere((k) => k.filter((x) => x !== item.key)); }}
                />
              ))}
            </div>
          </>
        )}
      </Sheet>

      <Sheet
        open={!!when}
        onClose={() => setWhen(null)}
        title={when?.mode === "move" ? "Move or remove" : "When do you want to go?"}
        subtitle={when && <b className="sheet-item">{when.item.name}</b>}
        footer={when && (
          <div className="sheet-actions">
            {when.mode === "move" && <button type="button" className="btn ghost danger-btn" onClick={removeFromWhen}>Remove from plan</button>}
            <button type="button" className="btn primary grow" onClick={confirmWhen}>
              {when.mode === "move" ? `Move to ${slotName(when.day, when.part)}` : `Add to ${slotName(when.day, when.part)}`}
            </button>
          </div>
        )}
      >
        {when && (
          <SlotPicker
            nights={nights}
            start={req.start_date}
            day={when.day}
            part={when.part}
            counts={counts}
            suggested={guessPart(when.item)}
            onDay={(d) => setWhen({ ...when, day: d })}
            onPart={(p) => setWhen({ ...when, part: p })}
          />
        )}
      </Sheet>
    </>
  );
  return { openAdd, openWhen, addNow, say, groups, ui };
}
