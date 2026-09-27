import { useEffect, useMemo, useRef, useState } from "react";
import { useTrip } from "../state/TripContext.jsx";
import { fetchRouteIdeas, fetchRoutePointNames, fetchRouteStops, trackDealClick } from "../api";
import { PARTS, PART_ICON, PART_LABEL } from "../lib/dayplan";
import { distanceM, duration, metres, money } from "../lib/format";
import { qualityLabel } from "../lib/stay";
import { dayDate, directionsUrl, nextUp, slotSuggestion } from "../lib/tripday";
import { PlannedRow, costText, placeDetailText, whereText } from "./PlanSheets.jsx";
import { connectionText } from "./FlightPicker.jsx";
import { CATEGORY_ICON, PartnerBadge } from "./DealCard.jsx";
import MapView from "./MapView.jsx";
import Photo from "./Photo.jsx";
import { useDealBooking } from "../state/DealBookingContext.jsx";
import { MOOD, MOODS, isOutdoor } from "../lib/moods";
import Sheet from "./Sheet.jsx";

const fmtDay = (iso, opts) => new Date(iso + "T00:00:00").toLocaleDateString("en-GB", opts);
const ROUTE_TYPE_OPTIONS = [
  ["attraction", "Attractions"],
  ["restaurant", "Restaurants"],
  ["historic", "Historic sites"],
  ["museum", "Museums"],
  ["park", "Parks"],
  ["viewpoint", "Viewpoints"],
  ["cafe", "Cafes"],
];
const ROUTE_TYPE_LABELS = Object.fromEntries(ROUTE_TYPE_OPTIONS);
const DEFAULT_ROUTE_RADIUS_M = 5000;
const DEFAULT_ROUTE_TYPES = ["attraction", "viewpoint", "historic", "museum", "park"];
const PART_PROGRESS = Object.fromEntries(PARTS.map((part, index) => [part, (index + 0.5) / PARTS.length]));
const PART_ROUTE_BANDS = Object.fromEntries(PARTS.map((part, index) => [part, [index / PARTS.length, (index + 1) / PARTS.length]]));
const ROUTE_SUGGESTION_MIN_SEPARATION_M = 2500;
const isGeneratedRoutePlaceholder = (item) => String(item?.name || "").startsWith("Find a real stop near ")
  || String(item?.name || "").startsWith("Find lunch or a sight near ")
  || String(item?.name || "").startsWith("Find an evening place near ")
  || String(item?.name || "").startsWith("Start from ");

function routePrefsFromText(text = "") {
  const lower = text.toLowerCase();
  const km = lower.match(/\b(\d+(?:\.\d+)?)\s*km\b/);
  const m = lower.match(/\b(\d{3,5})\s*m(?:eter|etre|eters|etres)?\b/);
  const radius_m = km ? Math.round(Number(km[1]) * 1000) : m ? Number(m[1]) : DEFAULT_ROUTE_RADIUS_M;
  const types = [];
  const add = (keys, type) => keys.some((k) => lower.includes(k)) && !types.includes(type) && types.push(type);
  add(["restaurant", "restaurants", "food", "dining"], "restaurant");
  add(["history", "historic", "heritage", "castle", "ruins"], "historic");
  add(["museum", "museums"], "museum");
  add(["park", "parks", "garden", "nature"], "park");
  add(["view", "viewpoint", "lookout"], "viewpoint");
  add(["cafe", "café", "coffee"], "cafe");
  return { radius_m: Math.max(500, Math.min(25000, radius_m || DEFAULT_ROUTE_RADIUS_M)), types };
}

function routePrefs(area = {}, label = "") {
  const inferred = routePrefsFromText(label || area.label || "");
  return {
    radius_m: area.radius_m || inferred.radius_m || DEFAULT_ROUTE_RADIUS_M,
    types: area.types?.length ? area.types : inferred.types.length ? inferred.types : DEFAULT_ROUTE_TYPES,
  };
}

const routePrefsText = (prefs) => `${Math.round((prefs.radius_m || DEFAULT_ROUTE_RADIUS_M) / 100) / 10} km corridor · ${(prefs.types || DEFAULT_ROUTE_TYPES).map((t) => ROUTE_TYPE_LABELS[t] || t).join(", ")}`;

function mentionedCountries(prompt, routeDestinations) {
  const text = (prompt || "").toLowerCase();
  const fromPrompt = [...new Set(routeDestinations.map((d) => d.country).filter((country) => country && text.includes(country.toLowerCase())))];
  return fromPrompt.length ? fromPrompt : [...new Set(routeDestinations.map((d) => d.country).filter(Boolean))];
}

function LocationSheet({ open, onClose, focusDay, trip, destinations, cityName, readback, applyDayFocus, say }) {
  const [draft, setDraft] = useState({});
  const [areaDraft, setAreaDraft] = useState({});
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const inputRefs = useRef({});
  const nights = trip?.it.nights || 0;
  const route = trip?.req.destinations?.length ? trip.req.destinations : [trip?.req.destination].filter(Boolean);
  const base = useMemo(() => {
    const out = { ...(trip?.dayLocations || {}) };
    if (trip) {
      for (let d = 1; d <= nights + 1; d += 1) out[d] ||= route.at(-1) || trip.req.destination;
    }
    return out;
  }, [trip, nights, route]);
  const current = { ...base, ...draft };
  const routeCodes = useMemo(() => {
    const seen = new Set();
    return [...route, ...Object.values(trip?.dayLocations || {})].filter((code) => {
      if (!code || seen.has(code)) return false;
      seen.add(code);
      return true;
    });
  }, [route, trip]);
  const routeDestinations = useMemo(
    () => routeCodes.map((code) => destinations.find((d) => d.code === code) || { code, city: cityName(code), country: "Trip route" }),
    [routeCodes, destinations, cityName],
  );
  const countries = useMemo(() => mentionedCountries(readback?.prompt, routeDestinations), [readback, routeDestinations]);
  const groups = useMemo(() => {
    const by = {};
    routeDestinations.forEach((d) => {
      const key = d.country || d.region || "Other";
      (by[key] ||= []).push(d);
    });
    Object.values(by).forEach((list) => list.sort((a, b) => a.city.localeCompare(b.city)));
    return Object.entries(by).sort(([a], [b]) => a.localeCompare(b));
  }, [routeDestinations]);
  const changeCountry = (day, country) => {
    const first = groups.find(([c]) => c === country)?.[1]?.[0];
    if (first) {
      setDraft((m) => ({ ...m, [day]: first.code }));
      setAreaDraft((m) => ({ ...m, [day]: { ...(m[day] || trip?.dayAreas?.[day] || {}), country } }));
    }
  };
  useEffect(() => {
    if (!open || !focusDay) return undefined;
    const t = setTimeout(() => {
      inputRefs.current[focusDay]?.scrollIntoView({ block: "center", behavior: "smooth" });
      inputRefs.current[focusDay]?.focus();
    }, 60);
    return () => clearTimeout(t);
  }, [open, focusDay]);
  const save = async () => {
    setSaving(true);
    setErr("");
    try {
      const areas = {};
      for (let day = 1; day <= nights + 1; day += 1) {
        const code = current[day] || route.at(-1);
        const dest = destinations.find((x) => x.code === code);
        const existing = trip?.dayAreas?.[day] || {};
        const edit = areaDraft[day] || {};
        const label = (edit.label ?? existing.label ?? "").trim();
        const country = edit.country || existing.country || dest?.country || "";
        if (label || country) areas[day] = { ...existing, country, label };
      }
      const kept = await applyDayFocus(current, areas);
      say?.(`Day route focus updated${kept?.keptFlight ? "" : ". Flight options changed"}`);
      setDraft({});
      setAreaDraft({});
      onClose();
    } catch (e) {
      setErr(e.message || "Could not update the route.");
    } finally {
      setSaving(false);
    }
  };
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={focusDay ? `Day ${focusDay} route / area` : "Plan days by route"}
      subtitle={<span className="muted">{focusDay ? "Tell this day where it starts, where it is heading, or the area you want to explore." : "Set the country and route focus for each day. The stay base is only for hotels and maps."}</span>}
      wide
      footer={<button type="button" className="btn primary full" onClick={save} disabled={saving}>{saving ? "Updating..." : "Update route and stays"}</button>}
    >
      <div className={`day-location-grid ${focusDay ? "single" : ""}`}>
        {(focusDay ? [focusDay] : Array.from({ length: nights + 1 }, (_, i) => i + 1)).map((day) => {
          const code = current[day] || route.at(-1) || "";
          const dest = destinations.find((x) => x.code === code);
          const area = { ...(trip?.dayAreas?.[day] || {}), ...(areaDraft[day] || {}) };
          const country = area.country || dest?.country || countries[0] || "";
          const cities = groups.find(([c]) => c === country)?.[1] || [];
          const label = area.label ?? "";
          return (
            <div key={day} className={`day-location-row ${focusDay === day ? "focus" : ""}`}>
              <b>Day {day}</b>
              <label className="select">
                <span>Country</span>
                <select value={country} onChange={(e) => changeCountry(day, e.target.value)}>
                  {countries.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>
              <label className="select">
                <span>Stay base</span>
                <select value={code} onChange={(e) => setDraft((m) => ({ ...m, [day]: e.target.value }))}>
                  {cities.map((d) => <option key={d.code} value={d.code}>{d.city}</option>)}
                </select>
              </label>
              <label className="select">
                <span>Route / area</span>
                {focusDay
                  ? (
                    <textarea
                      ref={(el) => { inputRefs.current[day] = el; }}
                      value={label}
                      maxLength={500}
                      rows={7}
                      placeholder={day <= nights ? `Example: ${cityName(code)} to Geneva via Dijon` : "Fly home day"}
                      onChange={(e) => setAreaDraft((m) => ({ ...m, [day]: { ...(m[day] || trip?.dayAreas?.[day] || {}), country, label: e.target.value } }))}
                    />
                  )
                  : (
                    <input
                      ref={(el) => { inputRefs.current[day] = el; }}
                      value={label}
                      maxLength={500}
                      placeholder={day <= nights ? `${cityName(code)} area or road route` : "Fly home day"}
                      onChange={(e) => setAreaDraft((m) => ({ ...m, [day]: { ...(m[day] || trip?.dayAreas?.[day] || {}), country, label: e.target.value } }))}
                    />
                  )}
              </label>
            </div>
          );
        })}
      </div>
      {err && <p className="err" role="alert">{err}</p>}
      <p className="fine">For a road day, write the route you mean, like Adelaide to Coober Pedy to Alice Springs. Attraction search still uses the catalog stops we can support, but the day itself no longer has to pretend it is one city.</p>
    </Sheet>
  );
}

/** A deal you booked (demo), in the time slot you chose. Tap it for the voucher, or to cancel. */
function BookedDealRow({ b, onOpen }) {
  return (
    <button type="button" className="planned-row booked-deal" onClick={() => onOpen(b)}>
      <span className="planned-thumb booked-icon" aria-hidden="true">{CATEGORY_ICON[b.deal.category] || "🏷️"}</span>
      <span className="planned-body">
        <b>{b.deal.title}</b>
        <small>{b.status === "redeemed" ? "✓ Used" : "✓ Booked"} · {money(b.total, b.currency)} {b.pay === "now" ? "paid" : b.status === "redeemed" ? "" : "to pay there"} · {b.reference}</small>
      </span>
      <span className="planned-more" aria-label="Voucher and cancel">⋯</span>
    </button>
  );
}

/** A partner deal along the day's route, with "Book" (a demo booking into this day). Labelled, and in the order the
 * server ranked it (never by payment). */
function RouteDeal({ deal, booked, onBook }) {
  return (
    <div className="route-deal-wrap">
    <a className="route-deal" href={deal.url} target="_blank" rel="noopener noreferrer sponsored" onClick={() => deal.id && trackDealClick(deal.id)}>
      <span className="route-deal-icon" aria-hidden="true">{CATEGORY_ICON[deal.category] || "🏷️"}</span>
      <span className="route-deal-body">
        <b>{deal.title}</b>
        <small>{metres(deal.distance_m)} from {deal.near} · {deal.partner_name}</small>
      </span>
      <span className="route-deal-price">
        {deal.discount_pct >= 10 && <em>−{deal.discount_pct}%</em>}
        <b>{money(deal.price, deal.currency || "GBP")}</b>
      </span>
      <PartnerBadge />
    </a>
    {booked ? <span className="flight-mine">✓ Booked</span> : <button type="button" className="btn primary sm" onClick={() => onBook(deal)}>Book</button>}
    </div>
  );
}

function Anchor({ icon, title, sub, action }) {
  return (
    <li className="tl-slot anchor">
      <div className="tl-mark" aria-hidden="true">{icon}</div>
      <div className="tl-content">
        <div className="anchor-row">
          <div className="anchor-body"><b>{title}</b>{sub && <small>{sub}</small>}</div>
          {action && <button type="button" className="tl-add-sm" onClick={action.run}>{action.label}</button>}
        </div>
      </div>
    </li>
  );
}

/** The whole trip, day by day: flights and stay as anchors, each time of day with what's planned (tap to move or
 * remove) or, if it's free, one fitting idea to add in a tap. Under each day, partner deals along that day's route
 * and a map of its stops. This is the page the traveler lives in, before and during the trip. */
export default function TripTimeline({ phase, dealsByDay, eventsByDate, sheets, onChangeFlight, weather }) {
  const { trip, cityName, tripId, moods, setMood, destinations, readback, applyDayFocus } = useTrip();
  const [moodDay, setMoodDay] = useState(null);
  const [locationsOpen, setLocationsOpen] = useState(false);
  const [locationFocusDay, setLocationFocusDay] = useState(null);
  const [routeEditDay, setRouteEditDay] = useState(null);
  const [routeDraft, setRouteDraft] = useState({});
  const [routePrefsDraft, setRoutePrefsDraft] = useState({});
  const [routeSaving, setRouteSaving] = useState(false);
  const [routeErr, setRouteErr] = useState("");
  const [routeStopsByDay, setRouteStopsByDay] = useState({});
  const [defaultRouteIdeasByDay, setDefaultRouteIdeasByDay] = useState({});
  const [routeBoundaryNames, setRouteBoundaryNames] = useState({});
  const [routePlaceFixes, setRoutePlaceFixes] = useState({});
  const [placeInfo, setPlaceInfo] = useState(null);
  const wx = (d) => weather?.days?.[dayDate(trip.req.start_date, d)] || null;
  const dealBooking = useDealBooking();
  const booked = dealBooking.forTrip(tripId);
  const bookedDealIds = new Set(booked.map((b) => b.deal.id));
  const [mapDay, setMapDay] = useState(null);
  const { it, req, hotel, chosenItems, candidates } = trip;
  const route = req.destinations?.length ? req.destinations : [req.destination];
  const tripRoutePath = ((it.route?.length ? it.route : route.map((code) => routeCity(code)).filter(Boolean)) || [])
    .filter((p) => p.lat != null && p.lng != null)
    .map((p) => ({ name: p.city || cityName(p.code), country: p.country || "", lat: p.lat, lng: p.lng, code: p.code }));
  const firstStop = route[0] || req.destination;
  const finalStop = route.at(-1) || req.destination;
  const originKnown = !readback || readback.said?.includes("origin") || readback.selected?.includes("origin");
  const flight = trip.flight;
  const nights = it.nights;
  const stayForDay = (d) => trip.staySegments?.find((s) => d >= s.start_day && d <= s.end_day);
  const cityForDay = (d) => trip.dayLocations?.[d] || stayForDay(d)?.destination || finalStop;
  const routeCity = (code) => destinations.find((x) => x.code === code);
  const routeBoundaryPoint = (index) => pointAlongRoute(tripRoutePath, index / Math.max(1, nights));
  const routeBoundaryFallbackName = (index) => {
    if (index <= 0) return tripRoutePath[0]?.name || cityName(firstStop);
    if (index >= nights) return tripRoutePath.at(-1)?.name || cityName(finalStop);
    const boundaryProgress = index / Math.max(1, nights);
    const endpointNames = new Set([cleanName(tripRoutePath[0]?.name), cleanName(tripRoutePath.at(-1)?.name), cleanName(cityName(firstStop)), cleanName(cityName(finalStop))].filter(Boolean));
    const ideas = Object.values(defaultRouteIdeasByDay).flat().filter((item) => item?.name && !isGeneratedRoutePlaceholder(item));
    const nearby = ideas
      .map((item) => ({
        ...item,
        delta: Math.abs(Number(item.global_route_progress ?? item.route_progress ?? 0.5) - boundaryProgress),
      }))
      .filter((item) => item.delta <= 0.24 && !endpointNames.has(cleanName(item.name)))
      .sort((a, b) => a.delta - b.delta || (a.distance_to_route_m ?? 0) - (b.distance_to_route_m ?? 0))[0];
    return nearby?.name || "";
  };
  const routeBoundaryName = (index) => routeBoundaryNames[index] || routeBoundaryFallbackName(index);
  const dayRouteLabelForDay = (d) => {
    const startName = routeBoundaryName(d - 1);
    const endName = routeBoundaryName(d);
    return startName && endName ? `${startName} to ${endName}` : "";
  };
  const cityPointForDay = (d) => {
    const code = cityForDay(d);
    const city = routeCity(code);
    return { name: city?.city || cityName(code), lat: city?.lat, lng: city?.lng };
  };
  const routeTargetForDay = (d, start = null) => {
    const namedStart = String(start?.name || "").toLowerCase();
    const current = cityForDay(d);
    const laterStay = (trip.staySegments || []).find((s) => s.start_day >= d && s.destination !== current);
    if (laterStay?.destination) return laterStay.destination;
    if (current && cityName(current).toLowerCase() !== namedStart) return current;
    if (finalStop && cityName(finalStop).toLowerCase() !== namedStart) return finalStop;
    return route.find((code) => {
      const name = cityName(code).toLowerCase();
      return code !== current && (!namedStart || ![name, String(code).toLowerCase()].includes(namedStart));
    });
  };
  const inferredRouteForDay = (d, start = null) => {
    if (trip.dayAreas?.[d]?.label?.trim() || d > nights) return null;
    const segment = routeSegmentForDay(d);
    if (segment?.label) {
      return { label: `Route section ${d}/${Math.max(1, nights)}`, country: routeCity(cityForDay(d))?.country || "" };
    }
    if (tripRoutePath.length > 1) return null;
    const from = start || previousEndpointForInference(d);
    const target = routeTargetForDay(d, from);
    if (!from?.name || !target) return null;
    const to = cityName(target);
    if (!to || to.toLowerCase() === String(from.name).toLowerCase()) return null;
    return { label: `${from.name} to ${to}`, country: routeCity(target)?.country || "" };
  };
  const routeAreaForDay = (d) => trip.dayAreas?.[d]?.label?.trim() || inferredRouteForDay(d)?.label || "";
  const routeCountryForDay = (d) => trip.dayAreas?.[d]?.country || inferredRouteForDay(d)?.country || routeCity(cityForDay(d))?.country || "";
  const focusForDay = (d) => routeAreaForDay(d) || cityName(cityForDay(d));
  const itemWhere = (item, day) => whereText(item) || focusForDay(day);
  const scheduled = new Set(chosenItems.map((i) => i.key));
  const taken = new Set(); // one idea is suggested in one empty slot only
  const knownCentre = it.guide?.center || (hotel.lat != null ? [hotel.lat, hotel.lng] : null);
  const live = phase.phase === "during";
  const next = live && phase.day <= nights ? nextUp(chosenItems, phase.day, phase.part) : null;
  const currentPosition = useCurrentPosition(live);
  const routeSegmentForDay = (d) => {
    if (d < 1 || d > nights || tripRoutePath.length < 2) return null;
    const startProgress = (d - 1) / Math.max(1, nights);
    const endProgress = d / Math.max(1, nights);
    const start = live && phase.day === d && hasPoint(currentPosition)
      ? { ...currentPosition, progress: startProgress }
      : pointAlongRoute(tripRoutePath, startProgress);
    const end = pointAlongRoute(tripRoutePath, endProgress);
    const inner = routeAnchorsBetween(tripRoutePath, startProgress, endProgress);
    const points = dedupePath([start, ...inner, end]);
    const label = segmentLabel(start, end, inner);
    return { start, end, points, startProgress, endProgress, label };
  };
  const fallbackDefaultsForDay = (d, path = []) => {
    const destination = cityForDay(d);
    const area = routeAreaForDay(d);
    if (!area) return [];
    const guideDefaults = candidates
      .filter((item) => !scheduled.has(item.key) && !item.fixed_day && (!item.destination || item.destination === destination))
      .slice(0, 16)
      .map((item, i, list) => ({
        ...item,
        source: "custom",
        fixed_day: d,
        area,
        city: area,
        route_progress: item.route_progress ?? (list.length > 1 ? i / (list.length - 1) : 0.5),
      }));
    return guideDefaults;
  };
  const routeDefaultForPart = (d, part, activePath = [], takenKeys = new Set()) => {
    const area = routeAreaForDay(d);
    if (!area) return null;
    const target = PART_PROGRESS[part] ?? 0.5;
    const [bandStart, bandEnd] = PART_ROUTE_BANDS[part] || [0, 1];
    const used = new Set(chosenItems.filter((item) => item.day === d).map((item) => item.key));
    const all = defaultRouteIdeasByDay[d] || [];
    const previouslySuggested = all.filter((item) => takenKeys.has(item.key));
    const real = all
      .filter((item) => !used.has(item.key)
        && !takenKeys.has(item.key)
        && hasPoint(item)
        && !String(item.key || "").startsWith("default-stage:")
        && item.route_progress != null
        && Number(item.route_progress) >= bandStart
        && (part === PARTS.at(-1) ? Number(item.route_progress) <= bandEnd : Number(item.route_progress) < bandEnd)
        && !previouslySuggested.some((picked) => sameRouteSuggestion(picked, item)))
      .sort((a, b) => Math.abs((a.route_progress ?? target) - target) - Math.abs((b.route_progress ?? target) - target))[0];
    if (real) {
      const segment = routeSegmentForDay(d);
      const dayPath = activePath.length > 1 ? activePath : segment?.points || [];
      const start = dayPath[0] || segment?.start;
      const along = routeDistanceAlongPath(dayPath, real.route_progress);
      return {
        ...real,
        default_part: part,
        fixed_day: d,
        area,
        city: area,
        distance_from_start_m: along ?? (hasPoint(start) ? Math.round(distanceM(start, real)) : real.distance_from_start_m ?? null),
      };
    }
    return routeFallbackActivityForPart(d, part, activePath);
  };
  const routeFallbackActivityForPart = (d, part, activePath = []) => {
    if (!routeAreaForDay(d)) return null;
    const segment = routeSegmentForDay(d);
    const points = (activePath.length > 1 ? activePath : segment?.points || []).filter(hasPoint);
    const progress = PART_PROGRESS[part] ?? 0.5;
    const point = points.length > 1
      ? pointAlongRoute(points, progress)
      : pointAlongRoute(tripRoutePath, ((d - 1) + progress) / Math.max(1, nights));
    const start = points[0] || segment?.start;
    const end = points.at(-1) || segment?.end;
    const startName = routeBoundaryName(d - 1) || routeEndpointName(start, "start");
    const endName = routeBoundaryName(d) || routeEndpointName(end, "end");
    const middleName = routeBoundaryName(d - 0.5) || "mid-route";
    const place = part === "morning" ? startName : part === "afternoon" ? middleName : endName;
    const labels = {
      morning: `Morning stop near ${place}`,
      afternoon: `Lunch stop ${place === "mid-route" ? "mid-route" : `near ${place}`}`,
      evening: `Evening sight near ${place}`,
      night: `Dinner or nightlife near ${place}`,
    };
    const tags = {
      morning: ["historic", "viewpoint"],
      afternoon: ["restaurant", "cafe"],
      evening: ["attraction", "viewpoint"],
      night: ["restaurant", "pub", "nightlife"],
    }[part] || ["route"];
    return {
      key: `route-fallback:${d}:${part}`,
      name: labels[part] || `Stop near ${place}`,
      why: "Default route suggestion until live places load",
      source: "custom",
      type: tags[0],
      typeLabel: "Route suggestion",
      tags,
      matches: tags.slice(0, 1),
      fixed_day: d,
      area: daySectionLabelForDay(d) || [startName, endName].filter(Boolean).join(" to "),
      city: daySectionLabelForDay(d) || "",
      route_stop: place,
      route_progress: progress,
      distance_from_start_m: routeDistanceAlongPath(points, progress),
      distance_to_route_m: 0,
      lat: point?.lat ?? null,
      lng: point?.lng ?? null,
      cost: null,
      duration: null,
    };
  };
  const routeIdeaFromPlace = (p, day, area, i, source = "default-route") => ({
    key: `${source}:${day}:${p.name}:${i}`,
    name: p.name,
    why: p.why || `Along ${area.label}`,
    source: "live-route",
    type: p.type || "route",
    typeLabel: p.typeLabel || "Along your route",
    tags: p.tags?.length ? p.tags : [p.type].filter(Boolean),
    matches: p.matches || [],
    fixed_day: day,
    area: area.label,
    route_stop: p.route_stop,
    distance_to_route_stop_m: p.distance_to_route_stop_m,
    distance_to_route_m: p.distance_to_route_m,
    route_progress: p.route_progress,
    global_route_progress: p.global_route_progress ?? p.route_progress,
    website: p.website,
    osm_url: p.osm_url,
    url: p.url,
    wikipedia: p.wikipedia,
    wikidata: p.wikidata,
    photo_url: p.photo_url,
    photo_credit: p.photo_credit,
    destination: null,
    city: area.label,
    lat: p.lat,
    lng: p.lng,
    cost: null,
    duration: null,
  });
  const splitWholeRouteIdeas = (places, areas) => {
    const byDay = Object.fromEntries(areas.map((area) => [area.day, []]));
    (places || []).forEach((place, i) => {
      const progress = Number.isFinite(Number(place.route_progress)) ? Math.max(0, Math.min(1, Number(place.route_progress))) : 0.5;
      const day = Math.min(nights, Math.max(1, Math.ceil(progress * nights)));
      const area = areas.find((a) => a.day === day);
      if (area) {
        const dayStart = (day - 1) / Math.max(1, nights);
        const dayEnd = day / Math.max(1, nights);
        const localProgress = dayEnd > dayStart ? (progress - dayStart) / (dayEnd - dayStart) : 0.5;
        byDay[day].push(routeIdeaFromPlace({ ...place, route_progress: Math.max(0, Math.min(1, localProgress)), global_route_progress: progress }, day, area, i, "whole-route"));
      }
    });
    return byDay;
  };
  const detailFor = (item, day) => {
    const display = routePlaceFixes[item.key] ? { ...item, ...routePlaceFixes[item.key], key: item.key, name: item.name } : item;
    const dayHotel = (stayForDay(day)?.hotel || hotel);
    const away = dayHotel?.lat != null && dayHotel?.lng != null && display.lat != null && display.lng != null
      ? metres(Math.round(Math.hypot((display.lat - dayHotel.lat) * 111_000, (display.lng - dayHotel.lng) * 78_000)))
      : null;
    return { item: display, raw: item, day, away };
  };
  const dayCentreFor = (d) => destinations.find((x) => x.code === cityForDay(d));
  const basePointForDay = (d) => {
    const dayHotel = (stayForDay(d)?.hotel || hotel);
    const centre = dayCentreFor(d);
    if (dayHotel?.lat != null) return { name: dayHotel.name, lat: dayHotel.lat, lng: dayHotel.lng };
    if (centre?.lat != null) return { name: centre.city || cityName(cityForDay(d)), lat: centre.lat, lng: centre.lng };
    return null;
  };
  const rawPathForDay = (d, stopsByDay = routeStopsByDay) => {
    const stops = (stopsByDay[d] || []).filter(hasPoint);
    if (stops.length) return stops;
    const segment = routeSegmentForDay(d);
    if (segment?.points?.length) return segment.points;
    const planned = chosenItems
      .filter((x) => x.day === d && hasPoint(routePlaceFixes[x.key] || x))
      .map((x) => ({ ...(routePlaceFixes[x.key] || x), name: x.name }));
    return planned.length ? planned : [basePointForDay(d)].filter(Boolean);
  };
  const explicitEndpointForDay = (d, stopsByDay = routeStopsByDay) => {
    if (d <= 0) return null;
    const stops = (stopsByDay[d] || []).filter(hasPoint);
    if (stops.length) return endOf(stops);
    const name = endpointNameFromRouteLabel(trip.dayAreas?.[d]?.label);
    return name ? { name } : null;
  };
  const previousEndpointForDay = (d, stopsByDay = routeStopsByDay) => (d > 1 ? (explicitEndpointForDay(d - 1, stopsByDay) || endOf(rawPathForDay(d - 1, stopsByDay))) : null);
  const previousEndpointForInference = (d) => (d > 1 ? (explicitEndpointForDay(d - 1) || cityPointForDay(d - 1)) : null);
  const startForDay = (d, stopsByDay = routeStopsByDay) => {
    const previous = previousEndpointForDay(d, stopsByDay);
    if (live && phase.day === d && hasPoint(currentPosition) && (!previous || distanceM(currentPosition, previous) > 1500)) return currentPosition;
    return previous;
  };
  const explicitRouteForDay = (d, fallback = "") => hasExplicitRouteText(fallback || routeAreaForDay(d) || focusForDay(d));
  const effectiveRouteLabelForDay = (d, fallback = "") => routeLabelWithStart(startForDay(d), fallback || routeAreaForDay(d) || focusForDay(d));
  const routeBoundaryAnchor = (progress, fallback, blockedName = "") => {
    if (progress <= 0) return tripRoutePath[0] || fallback;
    if (progress >= 1) return tripRoutePath.at(-1) || fallback;
    const ideas = Object.values(defaultRouteIdeasByDay)
      .flat()
      .filter((item) => hasPoint(item) && !isGeneratedRoutePlaceholder(item) && cleanName(item.name) !== cleanName(blockedName));
    const nearby = ideas
      .map((item) => ({ ...item, boundaryDelta: Math.abs(Number(item.global_route_progress ?? item.route_progress ?? 0.5) - progress) }))
      .filter((item) => item.boundaryDelta <= 0.18)
      .sort((a, b) => a.boundaryDelta - b.boundaryDelta || (a.distance_to_route_m ?? 0) - (b.distance_to_route_m ?? 0))[0];
    return nearby || fallback;
  };
  const routeSectionEndpointsForDay = (d) => {
    const segment = routeSegmentForDay(d);
    const startFallback = segment?.start || pointAlongRoute(tripRoutePath, (d - 1) / Math.max(1, nights));
    const start = routeBoundaryAnchor((d - 1) / Math.max(1, nights), startFallback);
    const endFallback = segment?.end || pointAlongRoute(tripRoutePath, d / Math.max(1, nights));
    const end = routeBoundaryAnchor(d / Math.max(1, nights), endFallback, start?.name);
    return { start, end };
  };
  const daySectionLabelForDay = (d) => {
    const startName = routeBoundaryName(d - 1);
    const endName = routeBoundaryName(d);
    return startName && endName ? `${startName} to ${endName}` : "";
  };
  const contextTextForItem = (item, day) => (
    item?.source === "live-route" || item?.source === "custom" || item?.area || item?.route_stop
      ? daySectionLabelForDay(day) || item.area || itemWhere(item, day)
      : itemWhere(item, day)
  );
  const saveInlineRoute = async (day) => {
    const label = (routeDraft[day] ?? trip.dayAreas?.[day]?.label ?? "").trim();
    const destination = destinations.find((x) => x.code === cityForDay(day));
    const areas = { ...(trip.dayAreas || {}) };
    const prefs = routePrefsDraft[day] || routePrefs(areas[day], label);
    if (label) areas[day] = { ...(areas[day] || {}), country: areas[day]?.country || destination?.country || "", label, radius_m: prefs.radius_m, types: prefs.types || [] };
    else delete areas[day];
    setRouteSaving(true);
    setRouteErr("");
    try {
      const kept = await applyDayFocus(trip.dayLocations || {}, areas);
      sheets.say?.(`Day ${day} route updated${kept?.keptFlight ? "" : ". Flight options changed"}`);
      setRouteEditDay(null);
    } catch (e) {
      setRouteErr(e.message || "Could not update this route.");
    } finally {
      setRouteSaving(false);
    }
  };

  useEffect(() => {
    let active = true;
    if (tripRoutePath.length < 2 || nights < 1) {
      setRouteBoundaryNames({});
      return () => {
        active = false;
      };
    }
    const load = async () => {
      const endpoints = {};
      const interior = [];
      for (let index = 0; index <= nights; index += 1) {
        const point = routeBoundaryPoint(index);
        if (!hasPoint(point)) continue;
        if (index === 0 || index === nights) {
          endpoints[index] = routeBoundaryFallbackName(index);
        } else {
          interior.push({ index, lat: point.lat, lng: point.lng });
        }
      }
      if (active) setRouteBoundaryNames(endpoints);
      try {
        const named = await fetchRoutePointNames({ points: interior });
        if (!active) return;
        const byIndex = {};
        (named.points || []).forEach((point) => {
          if (point.name) byIndex[point.index] = point.name;
        });
        setRouteBoundaryNames({ ...endpoints, ...byIndex });
      } catch {
        if (active) setRouteBoundaryNames(endpoints);
      }
    };
    setRouteBoundaryNames({});
    load();
    return () => {
      active = false;
    };
  }, [nights, req.destinations, it.route]);

  useEffect(() => {
    let active = true;
    const explicit = Object.entries(trip.dayAreas || {})
      .map(([day, area]) => ({ day: Number(day), label: area?.label?.trim(), country: area?.country || "" }))
      .filter((area) => area.day && area.label);
    const inferred = Array.from({ length: nights }, (_, i) => i + 1)
      .map((day) => ({ day, label: inferredRouteForDay(day)?.label || "", country: inferredRouteForDay(day)?.country || "" }))
      .filter((area) => area.day && area.label);
    const areas = [...explicit, ...inferred.filter((area) => !explicit.some((x) => x.day === area.day) && !routeSegmentForDay(area.day))];
    if (!areas.length) {
      setRouteStopsByDay({});
      return () => {
        active = false;
      };
    }
    Promise.all(areas.map((area) => (
      fetchRouteStops({ label: routeLabelWithStart(previousEndpointForInference(area.day), area.label), country: area.country })
        .then((r) => [area.day, r.stops || []])
        .catch(() => [area.day, []])
    ))).then((pairs) => {
      if (!active) return;
      const nextStops = Object.fromEntries(pairs);
      setRouteStopsByDay((prev) => (JSON.stringify(prev) === JSON.stringify(nextStops) ? prev : nextStops));
    });
    return () => {
      active = false;
    };
  }, [trip.dayAreas, currentPosition, nights, trip.staySegments, trip.dayLocations, req.destinations]);

  useEffect(() => {
    let active = true;
    const areas = Array.from({ length: nights }, (_, i) => i + 1)
      .map((day) => {
        const label = routeAreaForDay(day);
        const prefs = routePrefs(trip.dayAreas?.[day], label);
        return { day, label, country: routeCountryForDay(day), ...prefs };
      })
      .filter((area) => area.label);
    if (!areas.length) {
      setDefaultRouteIdeasByDay({});
      return () => {
        active = false;
      };
    }
    const explicitDays = new Set(Object.entries(trip.dayAreas || {})
      .filter(([, area]) => area?.label?.trim())
      .map(([day]) => Number(day)));
    const fullRouteAreas = tripRoutePath.length > 1 ? areas.filter((area) => !explicitDays.has(area.day)) : [];
    const dayAreas = fullRouteAreas.length === areas.length ? [] : areas.filter((area) => explicitDays.has(area.day) || !fullRouteAreas.some((x) => x.day === area.day));
    const requests = dayAreas.map((area) => (
      fetchRouteIdeas({
        label: effectiveRouteLabelForDay(area.day, area.label),
        country: area.country,
        types: (area.types || []).join(","),
        radius_m: area.radius_m || DEFAULT_ROUTE_RADIUS_M,
      })
        .then((r) => ({ [area.day]: (r.places || []).map((p, i) => routeIdeaFromPlace(p, area.day, area, i)) }))
        .catch(() => ({ [area.day]: [] }))
    ));
    if (fullRouteAreas.length) {
      const fullRouteLabel = tripRoutePath.map((point) => point.name).filter(Boolean).join(" to ");
      const countries = [...new Set(tripRoutePath.map((point) => point.country).filter(Boolean))];
      const types = [...new Set(fullRouteAreas.flatMap((area) => area.types || []))];
      const radius_m = Math.max(...fullRouteAreas.map((area) => area.radius_m || DEFAULT_ROUTE_RADIUS_M));
      requests.push(
        fetchRouteIdeas({
          label: fullRouteLabel,
          country: countries.length === 1 ? countries[0] : "",
          types: types.join(","),
          radius_m,
        })
          .then((r) => splitWholeRouteIdeas(r.places || [], fullRouteAreas))
          .catch(() => Object.fromEntries(fullRouteAreas.map((area) => [area.day, []]))),
      );
    }
    Promise.all(requests).then((chunks) => {
      if (!active) return;
      setDefaultRouteIdeasByDay(Object.assign({}, ...chunks));
    });
    return () => {
      active = false;
    };
  }, [trip.dayAreas, routeStopsByDay, currentPosition, nights, trip.staySegments, trip.dayLocations, req.destinations]);

  useEffect(() => {
    let active = true;
    const missing = chosenItems
      .filter((item) => item.lat == null && item.day && routeAreaForDay(item.day) && item.name)
      .map((item) => {
        const area = trip.dayAreas?.[item.day] || {};
        const prefs = routePrefs(area, routeAreaForDay(item.day));
        return { item, area: { label: routeAreaForDay(item.day), country: routeCountryForDay(item.day), ...prefs } };
      });
    if (!missing.length) {
      setRoutePlaceFixes({});
      return () => {
        active = false;
      };
    }
    Promise.all(missing.map(({ item, area }) => (
      fetchRouteIdeas({ label: effectiveRouteLabelForDay(item.day, area.label), country: area.country || "", q: item.name, types: (area.types || []).join(","), radius_m: area.radius_m || DEFAULT_ROUTE_RADIUS_M })
        .then((r) => {
          const clean = (s) => String(s || "").toLowerCase().trim();
          const exact = (r.places || []).find((p) => clean(p.name) === clean(item.name));
          const first = exact || (r.places || [])[0];
          return first?.lat != null ? [item.key, first] : null;
        })
        .catch(() => null)
    ))).then((pairs) => {
      if (active) setRoutePlaceFixes(Object.fromEntries(pairs.filter(Boolean)));
    });
    return () => {
      active = false;
    };
  }, [chosenItems, trip.dayAreas, routeStopsByDay, currentPosition, nights, trip.staySegments, trip.dayLocations, req.destinations]);

  /** A day's time slots as rows: planned items, a free slot with one fitting idea, or free slots merged into one. */
  const slotRows = (d, items, past, dayHotel, activePath = []) => {
    const rows = [];
    PARTS.forEach((p) => {
      const here = items.filter((x) => x.part === p);
      const deals = booked.filter((b) => b.day === d && b.part === p);
      if (here.length || deals.length) return rows.push({ kind: "filled", part: p, items: here, deals });
      const routeDefault = routeDefaultForPart(d, p, activePath, taken);
      if (!past && routeDefault) {
        taken.add(routeDefault.key);
        return rows.push({ kind: "idea", part: p, idea: { item: routeDefault, away: null, why: null } });
      }
      const routeDay = !!routeAreaForDay(d);
      const dayCandidates = routeDay ? (defaultRouteIdeasByDay[d] || []) : candidates;
      const idea = past ? null : slotSuggestion(dayCandidates, scheduled, taken, p, dayHotel, { day: d, destination: routeDay ? null : cityForDay(d), routeArea: routeDay ? daySectionLabelForDay(d) || routeAreaForDay(d) : "", mood: moods[d], wet: !!wx(d)?.wet });
      if (idea) return rows.push({ kind: "idea", part: p, idea });
      const prev = rows[rows.length - 1];
      if (prev?.kind === "free") prev.parts.push(p);
      else rows.push({ kind: "free", parts: [p] });
      return undefined;
    });
    return rows;
  };

  return (
    <div className="trip-days">
      {Array.from({ length: nights + 1 }, (_, i) => i + 1).map((d) => {
        const date = dayDate(req.start_date, d);
        const isToday = live && phase.day === d;
        const past = live && d < phase.day;
        const items = chosenItems.filter((x) => x.day === d && !isGeneratedRoutePlaceholder(x));
        const mapItems = items.map((x) => routePlaceFixes[x.key] ? { ...x, ...routePlaceFixes[x.key], key: x.key, name: x.name } : x);
        const deals = dealsByDay[d] || [];
        const events = eventsByDate[date] || [];
        const lastDay = d === nights + 1;
        const staySeg = stayForDay(d);
        const dayHotel = staySeg?.hotel || hotel;
        const routeFocus = routeAreaForDay(d);
        const routePrefsForDay = routePrefs(trip.dayAreas?.[d], routeFocus);
        const routeIsManual = !!trip.dayAreas?.[d]?.label?.trim();
        const routeSegment = routeSegmentForDay(d);
        const dayRouteLabel = daySectionLabelForDay(d);
        const sectionEndpoints = routeSectionEndpointsForDay(d);
        const routeStops = routeIsManual
          ? (routeStopsByDay[d] || [])
          : dedupePath([sectionEndpoints.start, ...(routeSegment?.points || []).slice(1, -1), sectionEndpoints.end]);
        const routePlanText = dayRouteLabel;
        const routeStart = explicitRouteForDay(d, routeFocus) ? null : startForDay(d);
        const activeMapPath = withStart(routeStart, routeStops);
        const dayStartName = routeBoundaryName(d - 1);
        const completedMapPath = d > 1 ? rawPathForDay(d - 1) : [];
        const plannedKeys = new Set(mapItems.map((x) => x.key));
        const routeIdeasForMap = [...(defaultRouteIdeasByDay[d] || []), ...(!routeFocus ? candidates : [])]
          .filter((x) => ["route", "live-route"].includes(x.source) && x.lat != null && (x.fixed_day === d || x.day === d) && !plannedKeys.has(x.key) && !isGeneratedRoutePlaceholder(x))
          .slice(0, 12);
        const routeIdeaPins = routeIdeasForMap
          .map((x) => {
            const withDistance = {
              ...x,
              distance_from_start_m: x.distance_from_start_m ?? routeDistanceAlongPath(activeMapPath, x.route_progress),
            };
            return { id: `route-idea-${x.key}`, kind: "venue", label: "", title: mapTitle(x.name, activeMapPath[0], withDistance), lat: x.lat, lng: x.lng, color: "#f5c76a" };
          });
        const routeStopPins = activeMapPath.map((s, n) => {
          const title = routeStopTitle(s, n, activeMapPath.length, activeMapPath[0]);
          return {
            id: `route-stop-${d}-${n}`,
            kind: samePoint(s, currentPosition) ? "you" : "sight",
            label: samePoint(s, currentPosition) ? "You" : String.fromCharCode(65 + n),
            title,
            lat: s.lat,
            lng: s.lng,
            color: samePoint(s, currentPosition) ? "#60a5fa" : "#f5c76a",
          };
        });
        const completedPins = completedMapPath.length && mapDay === d
          ? completedMapPath.map((s, n) => ({ id: `done-route-${d}-${n}`, kind: "venue", label: "", title: `Completed: ${s.name}`, lat: s.lat, lng: s.lng, color: "#94a3b8", zIndexOffset: 50 }))
          : [];
        const dayCentre = dayCentreFor(d);
        const mapCentre = dayCentre?.lat != null ? [dayCentre.lat, dayCentre.lng] : it.guide?.center || (dayHotel.lat != null ? [dayHotel.lat, dayHotel.lng] : null);
        const mapPath = activeMapPath.length > 1 ? activeMapPath : [];
        const mapPaths = [
          ...(completedMapPath.length > 1 ? [{ points: completedMapPath, color: "#94a3b8", weight: 3, opacity: 0.65, dashArray: "2 9" }] : []),
          ...(mapPath.length > 1 ? [{ points: mapPath, color: "#f5c76a", weight: 4, opacity: 0.95, dashArray: "8 8" }] : []),
        ];
        const routeSpan = mapPath.length > 1
          ? Math.max(...mapPath.map((p) => p.lat)) - Math.min(...mapPath.map((p) => p.lat))
            + Math.max(...mapPath.map((p) => p.lng)) - Math.min(...mapPath.map((p) => p.lng))
          : 0;
        const mapHeight = routeSpan > 1.2 ? 380 : 260;
        const fallbackPinPoint = basePointForDay(d);
        const suggestedMapTaken = new Set();
        const suggestedMapItems = !lastDay
          ? PARTS.filter((p) => !mapItems.some((x) => x.part === p)).map((p) => {
            const item = routeDefaultForPart(d, p, activeMapPath, suggestedMapTaken);
            if (item) suggestedMapTaken.add(item.key);
            return item ? { ...item, suggested: true } : null;
          }).filter((x) => x && x.lat != null && x.lng != null)
          : [];
        const plannedForPins = [...mapItems, ...suggestedMapItems].map((x, n) => {
          if (x.lat != null && x.lng != null) {
            return {
              ...x,
              distance_from_start_m: x.distance_from_start_m ?? routeDistanceAlongPath(activeMapPath, x.route_progress),
              mapLat: x.lat,
              mapLng: x.lng,
              approximate: false,
              plannedIndex: n,
            };
          }
          if (!fallbackPinPoint) return null;
          const angle = (-90 + (360 / Math.max(1, mapItems.length)) * n) * (Math.PI / 180);
          const radius = routeSpan > 1.2 ? 0.14 : 0.014;
          return {
            ...x,
            mapLat: fallbackPinPoint.lat + Math.sin(angle) * radius,
            mapLng: fallbackPinPoint.lng + Math.cos(angle) * radius,
            approximate: true,
            plannedIndex: n,
          };
        }).filter(Boolean);
        const spreadRadius = routeSpan > 1.2 ? 0.18 : 0.018;
        const plannedPins = plannedForPins.map((x, n) => {
          const spread = !x.approximate && plannedForPins.length > 1;
          const angle = (-90 + (360 / plannedForPins.length) * n) * (Math.PI / 180);
          return {
            id: x.key,
            kind: "sight",
            label: String((x.plannedIndex ?? n) + 1),
            title: x.approximate ? `${x.name} · approximate area` : mapTitle(x.name, activeMapPath[0], x),
            lat: x.mapLat,
            lng: x.mapLng,
            displayLat: spread ? x.mapLat + Math.sin(angle) * spreadRadius : x.mapLat,
            displayLng: spread ? x.mapLng + Math.cos(angle) * spreadRadius : x.mapLng,
            color: x.suggested ? "#f5c76a" : "#ffffff",
            zIndexOffset: x.suggested ? 760 : 900,
          };
        });
        const pins = [
          ...completedPins,
          ...routeStopPins,
          ...(dayHotel.lat != null ? [{ id: "hotel", kind: "hotel", label: "Stay", title: mapTitle(dayHotel.name, activeMapPath[0], dayHotel), lat: dayHotel.lat, lng: dayHotel.lng, color: "#2dd4bf", zIndexOffset: 250 }] : []),
          ...plannedPins,
          ...routeIdeaPins,
          ...deals.map((x) => ({ id: `deal-${x.id}`, kind: "venue", title: mapTitle(x.title, activeMapPath[0], x), lat: x.lat, lng: x.lng, color: "#f5c76a" })),
        ];
        const mapAvailable = pins.length > 1 || mapPath.length > 1 || completedMapPath.length > 1;
        return (
          <section key={d} id={`day-${d}`} className={`tday card pad ${isToday ? "today" : ""} ${past ? "past" : ""}`}>
            <header className="tday-head">
              <div className="tday-date">
                <b>Day {d}</b>
                <span>{fmtDay(date, { weekday: "long", day: "numeric", month: "short" })}</span>
                {isToday && <span className="tag hit">Today</span>}
                {lastDay && <span className="tag">Travel home</span>}
                {dayRouteLabel ? <span className="tag hit">{dayRouteLabel}</span> : routeFocus ? <span className="tag">Loading route places</span> : <span className="tag hit">{focusForDay(d)}</span>}
              </div>
              <div className="tday-tools">
              {wx(d) && (
                <span className={`wx-pill ${wx(d).wet ? "wet" : ""}`} title={`${wx(d).label} · Open-Meteo forecast`}>
                  {wx(d).icon} {wx(d).tmax != null ? `${wx(d).tmax}°` : ""}{wx(d).rain_pct != null && wx(d).rain_pct >= 20 ? ` · ${wx(d).rain_pct}%` : ""}
                </span>
              )}
              {!lastDay && !past && (
                <button type="button" className={`chip mood-chip ${moods[d] ? "set" : ""}`} onClick={() => setMoodDay(d)} aria-label={`Mood for Day ${d}`}>
                  {moods[d] ? `${MOOD[moods[d]].icon} ${MOOD[moods[d]].label}` : "🙂 Mood"}
                </button>
              )}
              {!past && (
                <button
                  type="button"
                  className="chip"
                  onClick={() => {
                    setRouteErr("");
                    const label = routeAreaForDay(d);
                    setRouteDraft((m) => ({ ...m, [d]: m[d] ?? label }));
                    setRoutePrefsDraft((m) => ({ ...m, [d]: m[d] || routePrefs(trip.dayAreas?.[d], label) }));
                    setRouteEditDay(routeEditDay === d ? null : d);
                  }}
                  aria-expanded={routeEditDay === d}
                  aria-controls={`day-${d}-route-editor`}
                  aria-label={`Change Day ${d} route focus`}
                >
                  📍 Area / route
                </button>
              )}
              {mapAvailable && (
                <button type="button" className="chip" aria-pressed={mapDay === d} onClick={() => setMapDay(mapDay === d ? null : d)}>
                  🗺️ {mapDay === d ? "Hide map" : "Map"}
                </button>
              )}
              </div>
            </header>
            {wx(d)?.wet && !past && (
              <p className="wx-banner">{wx(d).icon} {wx(d).label} likely{wx(d).rain_pct != null ? ` (${wx(d).rain_pct}% chance)` : ""}. Indoor ideas come first today{items.some(isOutdoor) ? ", and outdoor plans can be swapped" : ""}.</p>
            )}
            {staySeg && route.length > 1 && dayRouteLabel && (
              <p className="route-day-banner">{dayRouteLabel} · Stay base {cityName(staySeg.destination)} · {staySeg.hotel.name} · Day {staySeg.start_day}{staySeg.end_day !== staySeg.start_day ? `-${staySeg.end_day}` : ""}</p>
            )}
            {routeFocus && !lastDay && dayRouteLabel && (
              <p className="route-defaults">
                <b>{routeIsManual ? "Route plan" : "Default route plan"}</b>
                <span>{routePlanText} · {routePrefsText(routePrefsForDay)}</span>
              </p>
            )}

            {routeEditDay === d && (
              <div id={`day-${d}-route-editor`} className="route-inline-editor">
                <label className="field">
                  <span>Route / area for Day {d}</span>
                  <textarea
                    value={routeDraft[d] ?? ""}
                    rows={7}
                    maxLength={500}
                    autoFocus
                    placeholder={`Example: ${cityName(cityForDay(d))} to Geneva via Dijon`}
                    onChange={(e) => {
                      const label = e.target.value;
                      setRouteDraft((m) => ({ ...m, [d]: label }));
                      setRoutePrefsDraft((m) => ({ ...m, [d]: routePrefs(m[d], label) }));
                    }}
                  />
                </label>
                {(() => {
                  const prefs = routePrefsDraft[d] || routePrefs(trip.dayAreas?.[d], routeDraft[d] ?? trip.dayAreas?.[d]?.label ?? "");
                  const selected = new Set(prefs.types || []);
                  return (
                    <div className="route-prefs">
                      <label className="field route-radius">
                        <span>Max distance from main route</span>
                        <div className="route-radius-input">
                          <input
                            type="number"
                            min="0.5"
                            max="25"
                            step="0.5"
                            value={Number((prefs.radius_m || DEFAULT_ROUTE_RADIUS_M) / 1000)}
                            onChange={(e) => {
                              const km = Math.max(0.5, Math.min(25, Number(e.target.value) || 5));
                              setRoutePrefsDraft((m) => ({ ...m, [d]: { ...prefs, radius_m: Math.round(km * 1000) } }));
                            }}
                          />
                          <span>km</span>
                        </div>
                      </label>
                      <div className="route-type-picker">
                        <span>Find along the route</span>
                        <div className="chips">
                          {ROUTE_TYPE_OPTIONS.map(([key, text]) => (
                            <button
                              key={key}
                              type="button"
                              className="chip"
                              aria-pressed={selected.has(key)}
                              onClick={() => {
                                const next = new Set(selected);
                                if (next.has(key)) next.delete(key);
                                else next.add(key);
                                setRoutePrefsDraft((m) => ({ ...m, [d]: { ...prefs, types: [...next] } }));
                              }}
                            >
                              {text}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                  );
                })()}
                {routeErr && <p className="err" role="alert">{routeErr}</p>}
                <div className="route-inline-actions">
                  <button type="button" className="btn primary sm" onClick={() => saveInlineRoute(d)} disabled={routeSaving}>{routeSaving ? "Updating..." : "Update this day"}</button>
                  <button type="button" className="btn ghost sm" onClick={() => setRouteEditDay(null)}>Cancel</button>
                </div>
              </div>
            )}

            {mapDay === d && (
              <div className="tday-map">
                <MapView center={mapPath[0] ? [mapPath[0].lat, mapPath[0].lng] : (mapCentre || knownCentre || [pins[0].lat, pins[0].lng])} pins={pins} paths={mapPaths} height={mapHeight} onSelect={(id) => {
                  const found = mapItems.find((x) => x.key === id);
                  const suggested = suggestedMapItems.find((x) => x.key === id);
                  const routeIdea = routeIdeasForMap.find((x) => `route-idea-${x.key}` === id);
                  if (found) setPlaceInfo(detailFor(found, d));
                  else if (suggested) setPlaceInfo({ ...detailFor(suggested, d), planned: false });
                  else if (routeIdea) setPlaceInfo({ ...detailFor(routeIdea, d), planned: false });
                }} />
                <p className="fine">{routeFocus && dayRouteLabel ? `Showing ${dayRouteLabel}. ` : ""}{completedMapPath.length > 1 ? "Grey is the completed route from the previous day. " : ""}Letters are route stops. Numbers are your planned places. Small gold dots are other route ideas.</p>
              </div>
            )}

            <ol className="timeline">
              {d === 1 && (
                <>
                  <Anchor icon="✈️" title={originKnown ? `Fly ${cityName(req.origin)} → ${cityName(firstStop)}` : `Fly to ${cityName(firstStop)}`} sub={[!originKnown ? "Departure city was not in your request" : null, route.length > 1 ? `Route continues to ${cityName(finalStop)}` : null, flight.airline ? `${flight.airline} · ${connectionText(flight)}` : connectionText(flight), flight.duration_minutes && duration(flight.duration_minutes), flight.depart_time && `departs ${flight.depart_time}`].filter(Boolean).join(" · ")} action={trip.flights.length > 1 ? { label: "Change", run: onChangeFlight } : null} />
                  <Anchor icon="🏨" title={`Check in at ${dayHotel.name}`} sub={[qualityLabel(dayHotel), `${money(dayHotel.price_per_night)} a night`, cityName(cityForDay(d))].filter(Boolean).join(" · ")} />
                </>
              )}
              {!lastDay && slotRows(d, items, past, dayHotel, activeMapPath).map((row) => {
                if (row.kind === "filled") {
                  const p = row.part;
                  return (
                    <li key={p} className="tl-slot filled">
                      <div className="tl-mark" aria-hidden="true">{PART_ICON[p]}</div>
                      <div className="tl-content">
                        <div className="tl-head">
                          <span>{PART_LABEL[p]}</span>
                          <button type="button" className="tl-add-sm" onClick={() => sheets.openAdd(d, p)} aria-label={`Add more to Day ${d} ${PART_LABEL[p]}`}>+ Add</button>
                        </div>
                        {row.items.map((x) => {
                          const displayItem = routePlaceFixes[x.key] ? { ...x, ...routePlaceFixes[x.key], key: x.key, name: x.name } : x;
                          return (
                          <div key={x.key} className={next?.key === x.key ? "is-next" : ""}>
                            {next?.key === x.key && <span className="next-flag">Next</span>}
                            <PlannedRow
                              item={displayItem}
                              extra={placeDetailText(displayItem, contextTextForItem(displayItem, d))}
                              onOpen={() => setPlaceInfo(detailFor(x, d))}
                              onManage={() => sheets.openWhen(x, "move")}
                            />
                            {wx(d)?.wet && !past && isOutdoor(displayItem) && (
                              <div className="wx-swap">🌧️ Outdoors on a rainy day · <button type="button" className="linkbtn" onClick={() => sheets.openAdd(d, x.part, x)}>Swap for something indoors</button></div>
                            )}
                          </div>
                          );
                        })}
                        {row.deals.map((b) => <BookedDealRow key={b.reference} b={b} onOpen={dealBooking.openBooking} />)}
                      </div>
                    </li>
                  );
                }
                if (row.kind === "idea") {
                  const { part: p, idea } = row;
                  return (
                    <li key={p} className="tl-slot empty suggested">
                      <div className="tl-mark" aria-hidden="true">{PART_ICON[p]}</div>
                      <div className="tl-content">
                        <div className="free-row">
                          <span className="free-label">{PART_LABEL[p]} <em>suggested</em></span>
                          <button type="button" className="idea-chip" onClick={() => sheets.addNow(idea.item, { day: d, part: p })} title={idea.item.why}>
                            <span className="idea-plus">✓</span>
                            <span className="idea-chip-text"><b>{idea.item.name}</b><small>{[contextTextForItem(idea.item, d), idea.item.distance_from_start_m != null && dayStartName ? `${metres(idea.item.distance_from_start_m)} from ${dayStartName}` : null, idea.why === "indoors" ? "indoors, for the rain" : idea.why === "your mood" ? `fits your ${MOOD[moods[d]].label.toLowerCase()} mood` : null, idea.item.distance_from_start_m == null && idea.away != null ? `${metres(idea.away)} from your stay` : null].filter(Boolean).join(" · ")}</small></span>
                          </button>
                          <button type="button" className="linkbtn" onClick={() => sheets.openAdd(d, p)}>Change</button>
                        </div>
                      </div>
                    </li>
                  );
                }
                // consecutive free slots with nothing to suggest share one line
                return (
                  <li key={row.parts.join("-")} className="tl-slot empty">
                    <div className="tl-mark" aria-hidden="true">{PART_ICON[row.parts[0]]}</div>
                    <div className="tl-content">
                      <div className="free-row">
                        <span className="free-label">{row.parts.map((x) => PART_LABEL[x]).join(" · ")} <em>free</em></span>
                        {row.parts.map((x) => (
                          <button key={x} type="button" className="linkbtn" onClick={() => sheets.openAdd(d, x)}>+ {PART_LABEL[x]}</button>
                        ))}
                      </div>
                    </div>
                  </li>
                );
              })}
              {lastDay && (
                <>
                  {booked.filter((b) => b.day === d).map((b) => (
                    <li key={b.reference} className="tl-slot filled">
                      <div className="tl-mark" aria-hidden="true">{PART_ICON[b.part]}</div>
                      <div className="tl-content"><BookedDealRow b={b} onOpen={dealBooking.openBooking} /></div>
                    </li>
                  ))}
                  <Anchor icon="🧳" title={`Check out of ${(trip.staySegments?.at(-1)?.hotel || hotel).name}`} />
                  <Anchor icon="✈️" title={originKnown ? `Fly home ${cityName(finalStop)} → ${cityName(req.origin)}` : `Return flight from ${cityName(finalStop)}`} sub={`${originKnown ? "Return on the same booking" : "Departure city was not in your request"}${flight.airline ? ` · ${flight.airline}` : ""}`} action={trip.flights.length > 1 ? { label: "Change", run: onChangeFlight } : null} />
                </>
              )}
            </ol>

            {(deals.length > 0 || events.length > 0) && (
              <div className="tday-extra">
                {deals.length > 0 && (
                  <>
                    <div className="tday-extra-h">🏷️ On your way {isToday ? "today" : "this day"}</div>
                    {deals.map((x) => <RouteDeal key={x.id} deal={x} booked={bookedDealIds.has(x.id)} onBook={dealBooking.open} />)}
                  </>
                )}
                {events.length > 0 && (
                  <>
                    <div className="tday-extra-h">🎟️ On that night</div>
                    {events.slice(0, 2).map((e) => (
                      <a key={e.id} className="route-deal" href={e.url} target="_blank" rel="noopener noreferrer">
                        <span className="route-deal-icon" aria-hidden="true">🎟️</span>
                        <span className="route-deal-body"><b>{e.title}</b><small>{[e.venue, e.time].filter(Boolean).join(" · ")}</small></span>
                        {e.price_min != null && <span className="route-deal-price"><b>from {money(e.price_min, e.currency || "GBP")}</b></span>}
                      </a>
                    ))}
                  </>
                )}
              </div>
            )}
          </section>
        );
      })}
      <Sheet
        open={moodDay != null}
        onClose={() => setMoodDay(null)}
        title={moodDay ? `How do you feel on Day ${moodDay}?` : ""}
        subtitle={<span className="muted">Re-orders that day's ideas, deals along the way and pop-ups. Your interests stay as they are</span>}
      >
        <div className="mood-grid">
          {MOODS.map((m) => (
            <button key={m.key} type="button" className="mood-btn" aria-pressed={moods[moodDay] === m.key} onClick={() => { setMood(moodDay, m.key); setMoodDay(null); sheets.say(`Day ${moodDay}: ${m.label.toLowerCase()}. Ideas and deals re-ordered`); }}>
              <span aria-hidden="true">{m.icon}</span>{m.label}
            </button>
          ))}
          {moods[moodDay] && <button type="button" className="mood-btn clear" onClick={() => { setMood(moodDay, null); setMoodDay(null); }}>No particular mood</button>}
        </div>
      </Sheet>
      <Sheet
        open={!!placeInfo}
        onClose={() => setPlaceInfo(null)}
        title={placeInfo?.item?.name || "Place details"}
        subtitle={placeInfo?.item && <span className="muted">{placeDetailText(placeInfo.item, focusForDay(placeInfo.day))}</span>}
        footer={placeInfo && (
          <div className="sheet-actions">
            {placeInfo.item.lat != null && placeInfo.item.lng != null && (
              <a className="btn primary grow" href={directionsUrl(placeInfo.item)} target="_blank" rel="noopener noreferrer">Navigate</a>
            )}
            {placeInfo.planned === false
              ? <button type="button" className="btn ghost" onClick={() => { const raw = placeInfo.raw; setPlaceInfo(null); sheets.openWhen(raw, "add", placeInfo.day); }}>Add to plan</button>
              : <button type="button" className="btn ghost" onClick={() => { const raw = placeInfo.raw; setPlaceInfo(null); sheets.openWhen(raw, "move"); }}>Move / remove</button>}
          </div>
        )}
      >
        {placeInfo && (
          <div className="place-detail">
            {(placeInfo.item.photo || placeInfo.item.photo_url) && (
              <a href={placeInfo.item.photo_url || `/photos/${placeInfo.item.photo}.jpg`} target="_blank" rel="noreferrer" className="place-photo-link">
                <Photo k={placeInfo.item.photo} src={placeInfo.item.photo_url} info={placeInfo.item.photo_credit} alt={placeInfo.item.name} className="place-detail-photo" credit />
              </a>
            )}
            <div className="place-detail-grid">
              {placeInfo.item.typeLabel && <div><span>Type</span><b>{placeInfo.item.typeLabel}</b></div>}
              {placeInfo.item.distance_to_route_m != null && <div><span>Route</span><b>{metres(placeInfo.item.distance_to_route_m)} off route</b></div>}
              {placeInfo.item.route_stop && <div><span>Nearest route stop</span><b>{placeInfo.item.route_stop}</b></div>}
              {placeInfo.item.distance_to_route_stop_m != null && <div><span>From route stop</span><b>{metres(placeInfo.item.distance_to_route_stop_m)}</b></div>}
              {placeInfo.away && <div><span>From your stay</span><b>{placeInfo.away}</b></div>}
              {costText(placeInfo.item) && <div><span>Price</span><b>{costText(placeInfo.item)}</b></div>}
              {placeInfo.item.duration && <div><span>Duration</span><b>{placeInfo.item.duration}</b></div>}
            </div>
            {placeInfo.item.why && <p className="muted">{placeInfo.item.why}</p>}
            {!!(placeInfo.item.matches?.length || placeInfo.item.tags?.length) && (
              <div className="facts-row">
                {[...(placeInfo.item.matches || []), ...(placeInfo.item.tags || [])].slice(0, 6).map((t) => <span key={t} className="tag hit">{t}</span>)}
              </div>
            )}
            <div className="place-links">
              {placeInfo.item.website && <a className="btn ghost sm" href={placeInfo.item.website} target="_blank" rel="noreferrer">Website</a>}
              {placeInfo.item.url && <a className="btn ghost sm" href={placeInfo.item.url} target="_blank" rel="noreferrer">Article</a>}
              {placeInfo.item.osm_url && <a className="btn ghost sm" href={placeInfo.item.osm_url} target="_blank" rel="noreferrer">OpenStreetMap</a>}
              {placeInfo.item.photo_url && <a className="btn ghost sm" href={placeInfo.item.photo_url} target="_blank" rel="noreferrer">Open photo</a>}
            </div>
            {placeInfo.item.lat != null && placeInfo.item.lng != null && <p className="fine">Navigation opens Google Maps using this place's coordinates.</p>}
          </div>
        )}
      </Sheet>
      <LocationSheet open={locationsOpen} onClose={() => setLocationsOpen(false)} focusDay={locationFocusDay} trip={trip} destinations={destinations} cityName={cityName} readback={readback} applyDayFocus={applyDayFocus} say={sheets.say} />
    </div>
  );
}

const hasPoint = (p) => p?.lat != null && p?.lng != null;
const pointKey = (p) => hasPoint(p) ? `${Number(p.lat).toFixed(5)},${Number(p.lng).toFixed(5)}` : "";
const samePoint = (a, b) => pointKey(a) && pointKey(a) === pointKey(b);
const endOf = (points) => [...(points || [])].reverse().find(hasPoint) || null;
const withStart = (start, stops) => {
  const clean = (stops || []).filter(hasPoint);
  if (!hasPoint(start)) return clean;
  return clean.length && samePoint(start, clean[0]) ? clean : [start, ...clean];
};
const hasExplicitRouteText = (label) => /\bfrom\b.+\bto\b|.+\bto\b.+/i.test(String(label || ""));
const endpointNameFromRouteLabel = (label) => {
  const clean = String(label || "").trim();
  if (!clean) return "";
  const parts = clean.split(/\s+\bto\b\s+/i);
  if (parts.length < 2) return "";
  return parts.at(-1).split(/\s+\bvia\b\s+|\s+[–-]\s+|\s*,\s*/i)[0].trim();
};
const routeLabelWithStart = (start, label) => {
  const clean = String(label || "").trim();
  if (!clean || !start?.name) return clean;
  if (hasExplicitRouteText(clean)) return clean;
  return clean.toLowerCase().includes(String(start.name).toLowerCase()) ? clean : `${start.name} to ${clean}`;
};
const distanceFromStartText = (start, point) => {
  const startName = routeDisplayName(start, "route start");
  if (point?.distance_from_start_m != null) return `${metres(point.distance_from_start_m)} from ${startName}`;
  if (!hasPoint(start) || !hasPoint(point) || samePoint(start, point)) return null;
  return `${metres(Math.round(distanceM(start, point)))} from ${startName}`;
};
const mapTitle = (name, start, point) => [name, distanceFromStartText(start, point)].filter(Boolean).join(" · ");
const cleanName = (value) => String(value || "").trim().toLowerCase();
const isRouteInterpolation = (point) => !!point?.fromName && !!point?.toName;
const routeDisplayName = (point, fallback = "Route point") => {
  if (!point) return "";
  if (isRouteInterpolation(point)) return fallback;
  return point.name || fallback;
};
const routePointName = (point) => {
  if (!point) return "";
  return routeDisplayName(point, "Route point");
};
const routeEndpointName = (point, side = "start") => {
  if (!point) return side === "start" ? "Route start" : "Route end";
  if (isRouteInterpolation(point)) return side === "start" ? "day start" : "day end";
  return point.name || (side === "start" ? "Route start" : "Route end");
};
const routeStopTitle = (point, index, total, start) => {
  const title = routeDisplayName(point, index === 0 ? "Route start" : index === total - 1 ? "Route end" : "Route point");
  return mapTitle(title, start, point);
};
const cleanRoutePlanLabel = (points) => {
  const names = [];
  (points || []).forEach((point) => {
    const name = routePointName(point);
    if (name && names.at(-1) !== name) names.push(name);
  });
  return names.join(" -> ");
};
const sameRouteSuggestion = (a, b) => {
  if (!a || !b) return false;
  if (cleanName(a.name) && cleanName(a.name) === cleanName(b.name)) return true;
  return hasPoint(a) && hasPoint(b) && distanceM(a, b) < ROUTE_SUGGESTION_MIN_SEPARATION_M;
};

const routeLengths = (points) => {
  const lengths = [];
  let total = 0;
  for (let i = 0; i < points.length - 1; i += 1) {
    const len = distanceM(points[i], points[i + 1]);
    lengths.push(len);
    total += len;
  }
  return { lengths, total: total || 1 };
};

const routeDistanceAlongPath = (points, progress) => {
  const clean = (points || []).filter(hasPoint);
  if (clean.length < 2 || progress == null || !Number.isFinite(Number(progress))) return null;
  const { total } = routeLengths(clean);
  return Math.round(Math.max(0, Math.min(1, Number(progress))) * total);
};

const pointAlongRoute = (points, progress) => {
  const clean = (points || []).filter(hasPoint);
  if (!clean.length) return null;
  if (clean.length === 1) return { ...clean[0], progress: 0 };
  const clamped = Math.max(0, Math.min(1, progress));
  const { lengths, total } = routeLengths(clean);
  let left = clamped * total;
  for (let i = 0; i < lengths.length; i += 1) {
    const len = lengths[i];
    if (left <= len || i === lengths.length - 1) {
      const a = clean[i];
      const b = clean[i + 1];
      const t = len ? left / len : 0;
      const nearAnchor = t < 0.08 ? a : t > 0.92 ? b : null;
      const legName = `${a.name} to ${b.name}`;
      return {
        name: nearAnchor?.name || `${a.name} to ${b.name}`,
        legName,
        fromName: a.name,
        toName: b.name,
        lat: a.lat + (b.lat - a.lat) * t,
        lng: a.lng + (b.lng - a.lng) * t,
        progress: clamped,
      };
    }
    left -= len;
  }
  return { ...clean.at(-1), progress: 1 };
};

const segmentLabel = (start, end, inner = []) => {
  const first = routePointName(start);
  const last = routePointName(end);
  if (!first || !last) return "";
  const via = (inner || [])
    .map((p) => routePointName(p))
    .filter((name) => name && name !== first && name !== last);
  return [first, ...via, last].join(" to ");
};

const routeAnchorsBetween = (points, startProgress, endProgress) => {
  const clean = (points || []).filter(hasPoint);
  if (clean.length < 3) return [];
  const { lengths, total } = routeLengths(clean);
  let done = 0;
  return clean.slice(1, -1).map((point, i) => {
    done += lengths[i];
    return { ...point, progress: done / total };
  }).filter((point) => point.progress > startProgress && point.progress < endProgress);
};

const dedupePath = (points) => {
  const out = [];
  (points || []).filter(hasPoint).forEach((point) => {
    if (!out.some((p) => samePoint(p, point))) out.push(point);
  });
  return out;
};

function useCurrentPosition(active) {
  const [position, setPosition] = useState(null);
  useEffect(() => {
    if (!active || !navigator.geolocation) return undefined;
    let live = true;
    navigator.geolocation.getCurrentPosition(
      (pos) => live && setPosition({
        name: "Current location",
        lat: pos.coords.latitude,
        lng: pos.coords.longitude,
        accuracy: pos.coords.accuracy,
      }),
      () => live && setPosition(null),
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 120000 },
    );
    return () => {
      live = false;
    };
  }, [active]);
  return position;
}
