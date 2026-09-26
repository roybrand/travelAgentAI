import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTrip } from "../state/TripContext.jsx";
import { fetchRouteIdeas, fetchTonight } from "../api";
import { PARTS, PART_ICON, PART_LABEL, guessPart } from "../lib/dayplan";
import { TAG_LABEL } from "../lib/constants";
import { PLACE_TYPE_LABEL } from "../lib/profile";
import { metres, money } from "../lib/format";
import { dayDate, directionsUrl, slotScore } from "../lib/tripday";
import { MOOD, isIndoor, moodScore } from "../lib/moods";
import Photo from "./Photo.jsx";
import Sheet from "./Sheet.jsx";

const label = (t) => TAG_LABEL[t] || PLACE_TYPE_LABEL[t] || t;
const itemPhoto = (i) => ({ k: i.photo, src: i.photo_url, info: i.photo_credit });
const PART_HINT = { morning: "Good in the morning", afternoon: "Good in the afternoon", evening: "Good in the evening", night: "Good at night" };
export const slotName = (d, p) => `Day ${d} · ${PART_LABEL[p]}`;
export const costText = (i) => (i.cost == null ? null : i.cost ? `≈ ${money(i.cost)} pp` : "Free");
export const whereText = (i) => i.area || i.route_stop || i.city || i.destination || null;
export const placeDetailText = (i, fallback = null) => [
  i.typeLabel && i.typeLabel !== "Along your route" ? i.typeLabel : null,
  i.distance_to_route_m != null ? `${metres(i.distance_to_route_m)} off route` : null,
  i.route_stop && i.distance_to_route_m == null ? `near ${i.route_stop}` : null,
  i.distance_to_route_stop_m != null ? `${metres(i.distance_to_route_stop_m)} from route stop` : null,
  !i.route_stop ? whereText(i) : null,
  costText(i),
  i.duration,
].filter(Boolean).join(" · ") || fallback || i.why;
const dayLabel = (start, d, opts) => new Date(dayDate(start, d) + "T00:00:00").toLocaleDateString("en-GB", opts);
const clean = (s) => String(s || "").toLowerCase().replace(/[_-]+/g, " ").trim();

function isRouteAreaItem(item) {
  return item.source === "route" || item.source === "live-route" || item.area || item.route_stop || item.source === "custom" || item.source === "live-night";
}

function fitsDay(item, ctx = {}) {
  if (item.fixed_day && ctx.day && item.fixed_day !== ctx.day) return false;
  if (item.day && ctx.day && item.day !== ctx.day) return false;
  if (item.destination && ctx.destination && item.destination !== ctx.destination) return false;
  if (ctx.routeArea && !isRouteAreaItem(item)) return false;
  return true;
}

function ideaWords(item) {
  return [
    item.name, item.why, item.typeLabel, item.type, item.source, item.duration,
    whereText(item),
    ...(item.tags || []), ...(item.matches || []),
    costText(item), PART_LABEL[guessPart(item)],
  ].filter(Boolean);
}

function matchesIdea(item, query) {
  const q = clean(query);
  if (!q) return true;
  const words = ideaWords(item).map(clean);
  return q.split(/\s+/).every((part) => words.some((w) => w.includes(part)));
}

export function filterIdeaGroups(groups, query) {
  return groups.map((g) => ({ ...g, items: g.items.filter((item) => matchesIdea(item, query)) })).filter((g) => g.items.length > 0);
}

export function ideaSearchSuggestions(groups) {
  const seen = new Set();
  return groups.flatMap((g) => [
    g.label,
    ...g.items.flatMap((item) => ideaWords(item).filter((x) => String(x).length <= 36).map((x) => label(x))),
  ]).map((x) => String(x || "").trim()).filter((x) => x && !seen.has(x.toLowerCase()) && seen.add(x.toLowerCase())).slice(0, 80);
}

export function IdeaSearch({ value, onChange, groups, total, shown, placeholder = "Search ideas, e.g. beach, museum, rooftop" }) {
  const id = useId();
  const suggestions = useMemo(() => ideaSearchSuggestions(groups), [groups]);
  return (
    <div className="idea-search">
      <div className="idea-search-box">
        <span aria-hidden="true">⌕</span>
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          list={`${id}-ideas`}
          autoComplete="off"
          aria-label="Search ideas"
        />
        {value && <button type="button" className="idea-search-clear" onClick={() => onChange("")} aria-label="Clear search">×</button>}
      </div>
      <datalist id={`${id}-ideas`}>
        {suggestions.map((s) => <option key={s} value={s} />)}
      </datalist>
      <span className="idea-search-count">{value ? `${shown} of ${total}` : `${total} ideas`}</span>
    </div>
  );
}

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
    { key: "route", label: "Along your route", items: rest.filter((i) => i.source === "route") },
    { key: "sight", label: "Sights", items: rest.filter((i) => i.source === "sight") },
    { key: "adventure", label: "Adventures and nightlife", items: rest.filter((i) => i.source === "adventure") },
    ...byType.values(),
  ].filter((g) => g.items.length > 0);
}

/** Day and time-of-day chips: the one way to say "when" everywhere (adding, moving). */
function SlotPicker({ nights, start, day, part, onDay, onPart, counts, suggested, dayMeta = () => ({}) }) {
  return (
    <div className="slot-picker">
      <div className="slot-label">Day</div>
      <div className="slot-days">
        {Array.from({ length: nights }, (_, i) => i + 1).map((d) => {
          const meta = dayMeta(d);
          return (
            <button key={d} type="button" className="slot-day" aria-pressed={day === d} disabled={meta.disabled} title={meta.reason || ""} onClick={() => onDay(d)}>
              <b>Day {d}</b>
              <span>{meta.label || dayLabel(start, d, { weekday: "short", day: "numeric" })}</span>
              {counts[d] > 0 && <i>{counts[d]}</i>}
            </button>
          );
        })}
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

/** A planned item: clear context first, with move/remove and navigation actions separated. */
export function PlannedRow({ item, onOpen, onManage, extra }) {
  const canNavigate = item.lat != null && item.lng != null;
  return (
    <article className="planned-row">
      <Thumb item={item} className="planned-thumb" />
      <button type="button" className="planned-main" onClick={() => onOpen(item)}>
        <b>{item.name}</b>
        <small>{extra || placeDetailText(item)}</small>
      </button>
      <span className="planned-actions">
        {canNavigate && <a className="planned-nav" href={directionsUrl(item)} target="_blank" rel="noopener noreferrer" aria-label={`Navigate to ${item.name}`}>Directions</a>}
        <button type="button" className="planned-more" onClick={() => (onManage || onOpen)(item)} aria-label={`Move or remove ${item.name}`}>⋯</button>
      </span>
    </article>
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
          {whereText(item) && <span className="tag">{whereText(item)}</span>}
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
export function usePlanSheets({ onShowDay, dayContext = () => ({}) } = {}) {
  const { trip, toggleItem, moveItem } = useTrip();
  const [addSlot, setAddSlot] = useState(null); // { day, part } while the "add to this slot" sheet is open
  const [addedHere, setAddedHere] = useState([]); // keys added in the open sheet, so they stay visible with Undo
  const [filter, setFilter] = useState("fit");
  const [query, setQuery] = useState("");
  const [liveIdeas, setLiveIdeas] = useState([]);
  const [liveLoading, setLiveLoading] = useState(false);
  const [liveErr, setLiveErr] = useState("");
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
  const maxPlanDays = trip?.it.nights || 1;
  const scheduledKeys = useMemo(() => new Set(chosenItems.map((i) => i.key)), [chosenItems]);
  const counts = useMemo(() => chosenItems.reduce((m, i) => ({ ...m, [i.day]: (m[i.day] || 0) + 1 }), {}), [chosenItems]);
  const groups = useMemo(() => ideaGroups(candidates, scheduledKeys), [candidates, scheduledKeys]);

  /** Open ideas for one slot. `replace` (an item already there) makes it a swap: the first idea added takes its place. */
  const openAdd = useCallback((day, part, replace = null) => {
    const ctx = dayContext(day);
    setAddSlot({ day, part, replace });
    setAddedHere([]);
    setFilter(ctx.routeArea ? "route" : "fit");
    setQuery("");
    setLiveIdeas([]);
    setLiveErr("");
  }, [dayContext]);
  const openWhen = useCallback((item, mode, defaultDay = 1) => {
    const wanted = mode === "move" ? item.day : defaultDay;
    const valid = (d) => fitsDay(item, { day: d, ...dayContext(d) });
    const day = valid(wanted) ? wanted : Array.from({ length: maxPlanDays }, (_, i) => i + 1).find(valid) || wanted;
    setWhen({ item, mode, day, part: mode === "move" ? item.part : guessPart(item) });
  }, [dayContext, maxPlanDays]);
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
    const pool = [...candidates, ...liveIdeas].filter((c) => !scheduledKeys.has(c.key) || addedHere.includes(c.key));
    const matched = (i) => i.matches?.length > 0;
    const inFilter = (i) => {
      if (filter === "fit") return true;
      if (filter === "recommended") return matched(i);
      if (filter === "sight" || filter === "adventure") return !matched(i) && i.source === filter;
      if (filter === "route") return isRouteAreaItem(i);
      return !matched(i) && i.source === "place" && i.type === filter;
    };
    const ctx = { day: addSlot.day, ...dayContext(addSlot.day) };
    return pool
      .filter((i) => inFilter(i) && fitsDay(i, ctx) && matchesIdea(i, query))
      .sort((a, b) => slotScore(b, addSlot.part, ctx) - slotScore(a, addSlot.part, ctx));
  })();
  const sheetCtx = addSlot ? dayContext(addSlot.day) : {};
  const sheetTotal = addSlot ? [...candidates, ...liveIdeas].filter((c) => (!scheduledKeys.has(c.key) || addedHere.includes(c.key)) && fitsDay(c, { day: addSlot.day, ...sheetCtx })).length : 0;
  const canLiveSearch = addSlot && ["evening", "night"].includes(addSlot.part) && query.trim().length >= 2 && sheetCtx.destination;
  const canRouteSearch = addSlot && sheetCtx.routeArea;
  const routeSearchLabel = query.trim() ? `Search ${sheetCtx.routeArea} for "${query.trim().slice(0, 80)}"` : `Search along ${sheetCtx.routeArea}`;
  const hintFor = (item) => {
    if (sheetCtx.wet && isIndoor(item)) return "Indoors, good for rain";
    if (sheetCtx.mood && moodScore(item, sheetCtx.mood) >= 2) return `Fits your ${MOOD[sheetCtx.mood].label.toLowerCase()} mood`;
    return guessPart(item) === addSlot.part ? PART_HINT[addSlot.part] : null;
  };
  const addFromSheet = (item) => {
    if (addSlot.replace) {
      const old = addSlot.replace;
      toggleItem(old);
      toggleItem(item, addSlot);
      setAddSlot(null);
      say(`Swapped ${old.name} for ${item.name}`, { label: "Undo", run: () => { toggleItem(item); toggleItem(old, { day: old.day, part: old.part }); } });
      return;
    }
    toggleItem(item, addSlot);
    setAddedHere((k) => [...k, item.key]);
  };
  const addCustomFromQuery = () => {
    const name = query.trim().slice(0, 80);
    if (!name || !addSlot) return;
    const ctx = dayContext(addSlot.day);
    const item = {
      key: `custom:${addSlot.day}:${addSlot.part}:${Date.now()}`,
      name,
      why: "Your own idea",
      source: "custom",
      type: addSlot.part === "night" ? "nightlife" : "custom",
      typeLabel: "Custom idea",
      tags: addSlot.part === "night" ? ["nightlife"] : [],
      destination: ctx.destination || null,
      city: ctx.city || null,
      cost: null,
      duration: null,
    };
    toggleItem(item, addSlot);
    setAddedHere((k) => [...k, item.key]);
    setQuery("");
  };
  const liveSearch = async () => {
    if (!canLiveSearch) return;
    setLiveLoading(true);
    setLiveErr("");
    try {
      const q = clean(query);
      const kinds = q.includes("club") || q.includes("party") || q.includes("dance") || q.includes("techno") ? "clubs,bars" : "bars,clubs";
      const plannedDate = dayDate(req.start_date, addSlot.day);
      const daysAhead = Math.round((new Date(plannedDate + "T00:00:00") - new Date(new Date().toISOString().slice(0, 10) + "T00:00:00")) / 86400000);
      const r = await fetchTonight({ dest: sheetCtx.destination, date: daysAhead >= 0 && daysAhead <= 14 ? plannedDate : undefined, kinds });
      const city = r.city || sheetCtx.city;
      const venues = (r.venues || []).map((v, i) => ({
        key: `live-night:${sheetCtx.destination}:${v.name}:${i}`,
        name: v.name,
        why: [v.kind_label, ...(v.why || [])].filter(Boolean).join(" · ") || "Live nightlife result",
        source: "live-night",
        type: v.type || "nightlife",
        typeLabel: v.kind_label || "Nightlife",
        tags: ["nightlife", "party"],
        destination: sheetCtx.destination,
        city,
        lat: v.lat,
        lng: v.lng,
        cost: v.price ?? null,
        duration: "night",
        photo_url: v.photo_url,
        photo_credit: v.photo_credit,
      }));
      const events = (r.events || []).map((e, i) => ({
        key: `live-event:${sheetCtx.destination}:${e.id || e.title}:${i}`,
        name: e.title,
        why: [e.venue, e.time].filter(Boolean).join(" · ") || "Live event",
        source: "live-night",
        type: "event",
        typeLabel: "Event",
        tags: ["nightlife", "party"],
        destination: sheetCtx.destination,
        city,
        cost: e.price_min ?? null,
        duration: e.time || "night",
      }));
      const next = [...venues, ...events].filter((item) => matchesIdea(item, query) || !venues.length);
      setLiveIdeas(next);
      if (!next.length) setLiveErr(`No live nightlife results found for ${city || "this city"} yet.`);
    } catch (e) {
      setLiveErr(e.message || "Could not search live nightlife right now.");
    } finally {
      setLiveLoading(false);
    }
  };
  const routeSearch = async () => {
    if (!canRouteSearch) return;
    setLiveLoading(true);
    setLiveErr("");
    try {
      const r = await fetchRouteIdeas({ label: sheetCtx.routeArea, country: sheetCtx.country, q: query, types: (sheetCtx.routeTypes || []).join(","), radius_m: sheetCtx.routeRadiusM });
      const next = (r.places || []).map((p, i) => ({
        key: `live-route:${addSlot.day}:${p.name}:${i}`,
        name: p.name,
        why: p.why || `Along ${sheetCtx.routeArea}`,
        source: "live-route",
        type: p.type || "route",
        typeLabel: p.typeLabel || "Along your route",
        tags: p.tags?.length ? p.tags : [p.type, clean(query)].filter(Boolean),
        matches: p.matches?.length ? p.matches : [clean(query)].filter(Boolean),
        fixed_day: addSlot.day,
        area: sheetCtx.routeArea,
        route_stop: p.route_stop,
        distance_to_route_stop_m: p.distance_to_route_stop_m,
        distance_to_route_m: p.distance_to_route_m,
        route_progress: p.route_progress,
        website: p.website,
        osm_url: p.osm_url,
        url: p.url,
        wikipedia: p.wikipedia,
        wikidata: p.wikidata,
        photo_url: p.photo_url,
        photo_credit: p.photo_credit,
        destination: null,
        city: sheetCtx.routeArea,
        lat: p.lat,
        lng: p.lng,
        cost: null,
        duration: null,
      }));
      setLiveIdeas(next);
      if (!next.length) setLiveErr(`No route results found for ${query.trim()} around ${sheetCtx.routeArea}.`);
    } catch (e) {
      setLiveErr(e.message || "Could not search this route right now.");
    } finally {
      setLiveLoading(false);
    }
  };

  const closeAdd = () => {
    if (addedHere.length) say(`${addedHere.length} added to ${slotName(addSlot.day, addSlot.part)}`);
    setAddSlot(null);
  };
  const confirmWhen = () => {
    const { item, mode, day: d, part: p } = when;
    if (!fitsDay(item, { day: d, ...dayContext(d) })) {
      say(`${item.name} belongs to ${whereText(item) || "another route day"}. Choose a matching day.`);
      return;
    }
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
        title={addSlot ? (addSlot.replace ? `Swap ${addSlot.replace.name}` : `Add to ${slotName(addSlot.day, addSlot.part)}`) : ""}
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
              {sheetCtx.routeArea && !groups.some((g) => g.key === "route") && (
                <button type="button" className="chip" aria-pressed={filter === "route"} onClick={() => setFilter("route")}>Along this route</button>
              )}
              {groups.map((g) => (
                <button key={g.key} type="button" className="chip" aria-pressed={filter === g.key} onClick={() => setFilter(g.key)}>{g.label}</button>
              ))}
            </div>
            <IdeaSearch
              value={query}
              onChange={setQuery}
              groups={groups}
              total={sheetTotal}
              shown={sheetIdeas.length}
              placeholder={sheetCtx.routeArea ? `Search ${sheetCtx.routeArea}, e.g. parks, castles, cafes` : "Search or add your own, e.g. party, club, jazz bar"}
            />
            {sheetCtx.routeArea && (
              <button type="button" className="custom-idea-btn live-search-btn" onClick={routeSearch} disabled={!canRouteSearch || liveLoading}>
                <span className="idea-plus">⌕</span>
                <span><b>{liveLoading ? "Searching route..." : routeSearchLabel}</b><small>{sheetCtx.label || `Day ${addSlot.day}`}</small></span>
              </button>
            )}
            {canLiveSearch && (
              <button type="button" className="custom-idea-btn live-search-btn" onClick={liveSearch} disabled={liveLoading}>
                <span className="idea-plus">⌕</span>
                <span><b>{liveLoading ? "Searching nightlife..." : `Search live nightlife for "${query.trim().slice(0, 80)}"`}</b><small>{sheetCtx.label || `Day ${addSlot.day}`}</small></span>
              </button>
            )}
            {liveErr && <p className="fine">{liveErr}</p>}
            {sheetIdeas.length === 0 && (
              <p className="muted">
                {sheetCtx.routeArea
                  ? (query ? "No saved ideas match yet. Use the route search above or add it as your own idea." : "Type what you want along this route, like parks, castles or cafes.")
                  : (query ? "No ideas match that search here. Try another word or clear search." : "Nothing left to add here. Try another group.")}
              </p>
            )}
            {query.trim().length >= 2 && (
              <button type="button" className="custom-idea-btn" onClick={addCustomFromQuery}>
                <span className="idea-plus">+</span>
                <span><b>Add "{query.trim().slice(0, 80)}"</b><small>Custom idea for {slotName(addSlot.day, addSlot.part)}</small></span>
              </button>
            )}
            <div className="idea-list">
              {sheetIdeas.map((item) => (
                <IdeaRow
                  key={item.key}
                  item={item}
                  hint={hintFor(item)}
                  added={addedHere.includes(item.key)}
                  addLabel={addSlot.replace ? "Swap in" : "+ Add"}
                  onAdd={() => addFromSheet(item)}
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
            dayMeta={(d) => {
              const ctx = { day: d, ...dayContext(d) };
              const disabled = !fitsDay(when.item, ctx);
              return { disabled, label: ctx.label || ctx.city || dayLabel(req.start_date, d, { weekday: "short", day: "numeric" }), reason: disabled ? `${whereText(when.item) || "This idea"} is not on Day ${d}'s route` : "" };
            }}
            onDay={(d) => setWhen({ ...when, day: d })}
            onPart={(p) => setWhen({ ...when, part: p })}
          />
        )}
      </Sheet>
    </>
  );
  return { openAdd, openWhen, addNow, say, groups, ui };
}
