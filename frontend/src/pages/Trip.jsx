import { useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { useTrip } from "../state/TripContext.jsx";
import { fetchDeals, fetchEvents, fetchTripWeather } from "../api";
import { DISCLOSURE } from "../components/DealsSection.jsx";
import { TAG_LABEL } from "../lib/constants";
import { MONTHS, duration, money, shortDate } from "../lib/format";
import { qualityLabel } from "../lib/stay";
import { PLACE_TYPE_LABEL } from "../lib/profile";
import { dayDate, routeDeals, tripPhase } from "../lib/tripday";
import StayDetail from "../components/StayDetail.jsx";
import Photo from "../components/Photo.jsx";
import SaveTripBar from "../components/SaveTripBar.jsx";
import SourceBadge from "../components/SourceBadge.jsx";
import CareCard from "../components/CareCard.jsx";
import TripTimeline from "../components/TripTimeline.jsx";
import PlanBar from "../components/PlanBar.jsx";
import { IdeaRow, IdeaSearch, filterIdeaGroups, usePlanSheets } from "../components/PlanSheets.jsx";
import { useDealBooking } from "../state/DealBookingContext.jsx";
import FlightPicker, { connectionText } from "../components/FlightPicker.jsx";
import TravelersSheet from "../components/TravelersSheet.jsx";
import InterestsSheet from "../components/InterestsSheet.jsx";
import TicketsSheet from "../components/TicketsSheet.jsx";
import AccountPanel from "../components/AccountPanel.jsx";
import MapView from "../components/MapView.jsx";

const C = { flight: "#818cf8", stay: "#2dd4bf", exp: "#f5c76a" };
const DEFAULT_ROUTE_RADIUS_M = 5000;
const DEFAULT_ROUTE_TYPES = ["attraction", "viewpoint", "historic", "museum", "park"];

function routePrefsFromText(text = "") {
  const lower = text.toLowerCase();
  const km = lower.match(/\b(\d+(?:\.\d+)?)\s*km\b/);
  const m = lower.match(/\b(\d{3,5})\s*m(?:eter|etre|eters|etres)?\b/);
  const types = [];
  const add = (keys, type) => keys.some((k) => lower.includes(k)) && !types.includes(type) && types.push(type);
  add(["restaurant", "restaurants", "food", "dining"], "restaurant");
  add(["history", "historic", "heritage", "castle", "ruins"], "historic");
  add(["museum", "museums"], "museum");
  add(["park", "parks", "garden", "nature"], "park");
  add(["view", "viewpoint", "lookout"], "viewpoint");
  add(["cafe", "café", "coffee"], "cafe");
  return {
    radius_m: Math.max(500, Math.min(25000, km ? Math.round(Number(km[1]) * 1000) : m ? Number(m[1]) : DEFAULT_ROUTE_RADIUS_M)),
    types,
  };
}

function routePrefs(area = {}, label = "") {
  const inferred = routePrefsFromText(label || area.label || "");
  return {
    routeRadiusM: area.radius_m || inferred.radius_m || DEFAULT_ROUTE_RADIUS_M,
    routeTypes: area.types?.length ? area.types : inferred.types.length ? inferred.types : DEFAULT_ROUTE_TYPES,
  };
}

const endpointNameFromRouteLabel = (label) => {
  const clean = String(label || "").trim();
  if (!clean) return "";
  const parts = clean.split(/\s+\bto\b\s+/i);
  if (parts.length < 2) return "";
  return parts.at(-1).split(/\s+\bvia\b\s+|\s+[–-]\s+|\s*,\s*/i)[0].trim();
};

/** One line per part of the trip, split by whether the person's words gave it or the form did. */
function readbackLines(said, req, cityName, routeName, fromWords) {
  const has = (k) => said.includes(k);
  const parts = [
    ...(has("origin") ? [["origin", `Flying from ${cityName(req.origin)}`, true]] : []),
    ["destination", `Route: ${routeName(req)}`, has("destinations") || has("destination")],
    ["dates", `${shortDate(req.start_date)} to ${shortDate(req.end_date)}`, has("start_date")],
    ["travelers", `${req.travelers} traveler${req.travelers > 1 ? "s" : ""}`],
    ["budget", req.budget ? `Budget ${money(req.budget)}` : "No budget set"],
    ["interests", req.interests.length ? `Interests: ${req.interests.map((i) => TAG_LABEL[i] || i).join(", ")}` : "No interests set"],
  ];
  return parts.filter(([k, , explicit]) => (explicit ?? has(k)) === fromWords).map(([, line]) => line);
}

/** A folded section of "Trip details": everything that explains the trip, kept out of the way of the plan itself. */
function Fold({ title, hint, children, open = false }) {
  return (
    <details className="fold card" open={open}>
      <summary><b>{title}</b>{hint && <span className="muted">{hint}</span>}</summary>
      <div className="fold-body">{children}</div>
    </details>
  );
}

/** The trip, as the traveler lives it: a slim header, a card that looks after them, and the itinerary day by day,
 * editable in place, with partner deals along each day's route. Everything else sits folded under Trip details. */
export default function Trip() {
  const { trip, cityName, routeName, profile, forgetProfile, config, resetSearch, readback, booking, savedTrip, destinations, choosePackage, moods } = useTrip();
  const [weather, setWeather] = useState(null);
  const [flightsOpen, setFlightsOpen] = useState(false);
  const [travelersOpen, setTravelersOpen] = useState(false);
  const [likesOpen, setLikesOpen] = useState(false);
  const [ticketsOpen, setTicketsOpen] = useState(false);
  const dealBooking = useDealBooking();
  const navigate = useNavigate();
  const [activeDay, setActiveDay] = useState(1);
  const [deals, setDeals] = useState([]);
  const [events, setEvents] = useState([]);
  const [ideaQuery, setIdeaQuery] = useState("");
  const stripRef = useRef(null);
  const req = trip?.req;

  const scrollToDay = (d) => {
    setActiveDay(d);
    const el = document.getElementById(`day-${d}`);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    el.classList.remove("flash");
    void el.offsetWidth; // restart the highlight animation
    el.classList.add("flash");
  };
  const wetOn = (d) => !!(trip && weather?.days?.[dayDate(trip.req.start_date, d)]?.wet);
  const dayDestination = (d) => trip?.dayLocations?.[d] || trip?.staySegments?.find((s) => d >= s.start_day && d <= s.end_day)?.destination || req?.destination;
  const inferredRouteFocus = (d) => {
    if (!trip || trip.dayAreas?.[d]?.label?.trim() || d <= 1 || d > (trip.it.nights || 0)) return null;
    const from = endpointNameFromRouteLabel(trip.dayAreas?.[d - 1]?.label);
    if (!from) return null;
    const route = trip.req.destinations?.length ? trip.req.destinations : [trip.req.destination];
    const current = dayDestination(d);
    const target = (trip.staySegments || []).find((s) => s.start_day >= d && s.destination !== current)?.destination
      || (current && cityName(current).toLowerCase() !== from.toLowerCase() ? current : null)
      || (route.at(-1) && cityName(route.at(-1)).toLowerCase() !== from.toLowerCase() ? route.at(-1) : null)
      || route.find((code) => cityName(code).toLowerCase() !== from.toLowerCase() && code !== current);
    const to = target ? cityName(target) : "";
    if (!to || to.toLowerCase() === from.toLowerCase()) return null;
    return { label: `${from} to ${to}`, country: destinations.find((x) => x.code === target)?.country || "" };
  };
  const sheets = usePlanSheets({ onShowDay: scrollToDay, dayContext: (d) => {
    const destination = dayDestination(d);
    const inferred = inferredRouteFocus(d);
    const routeArea = trip?.dayAreas?.[d]?.label?.trim() || inferred?.label || "";
    const country = trip?.dayAreas?.[d]?.country || inferred?.country || destinations.find((x) => x.code === destination)?.country || "";
    return { day: d, destination, country, routeArea, ...routePrefs(trip?.dayAreas?.[d], routeArea), label: `${routeArea || cityName(destination)} · ${shortDate(dayDate(trip.req.start_date, d))}`, mood: moods[d], wet: wetOn(d) };
  } });

  const nights = trip?.it.nights || 0;
  const phase = useMemo(() => (req ? tripPhase(req, nights) : null), [req, nights]);

  // Partner deals and events for the trip's city and dates, placed on the days whose route they lie along.
  useEffect(() => {
    if (!req) return undefined;
    let live = true;
    fetchDeals({ dest: req.destination, start: req.start_date, end: req.end_date, interests: req.interests.join(","), place_types: (req.place_types || []).join(",") })
      .then((r) => live && setDeals(r.deals || []))
      .catch(() => live && setDeals([]));
    fetchTripWeather({ dest: req.destination, start: req.start_date, end: dayDate(req.start_date, (trip?.it.nights || 0) + 1) })
      .then((r) => live && setWeather(r))
      .catch(() => live && setWeather(null));
    if (config.ticketmaster) {
      fetchEvents({ dest: req.destination, start: req.start_date, end: req.end_date })
        .then((r) => live && setEvents(r.events || []))
        .catch(() => {});
    }
    return () => {
      live = false;
    };
  }, [req, config.ticketmaster]);

  // The day chip follows the day being read.
  useEffect(() => {
    if (!trip) return undefined;
    const seen = new IntersectionObserver((entries) => {
      entries.forEach((e) => e.isIntersecting && setActiveDay(Number(e.target.id.slice(4))));
    }, { rootMargin: "-35% 0px -55% 0px" });
    document.querySelectorAll(".tday").forEach((el) => seen.observe(el));
    return () => seen.disconnect();
  }, [trip]);
  useEffect(() => {
    stripRef.current?.querySelector(`[data-day="${activeDay}"]`)?.scrollIntoView({ block: "nearest", inline: "center", behavior: "smooth" });
  }, [activeDay]);

  const dealsByDay = useMemo(() => {
    if (!trip) return {};
    return routeDeals(deals, {
      days: Array.from({ length: nights + 1 }, (_, i) => i + 1), startIso: req.start_date, items: trip.chosenItems, hotel: trip.hotel,
      centre: destinations.find((x) => x.code === req.destination),
      hotelForDay: (d) => trip.staySegments?.find((s) => d >= s.start_day && d <= s.end_day)?.hotel || trip.hotel,
      centreForDay: (d) => destinations.find((x) => x.code === (trip.dayLocations?.[d] || req.destination)),
      pinDay: phase?.phase === "during" ? phase.day : null,
      moodFor: (d) => moods[d],
    });
  }, [deals, trip, nights, req, phase, destinations, moods]);
  const eventsByDate = useMemo(() => events.reduce((m, e) => ({ ...m, [e.date]: [...(m[e.date] || []), e] }), {}), [events]);
  const visibleIdeaGroups = useMemo(() => filterIdeaGroups(sheets.groups, ideaQuery), [sheets.groups, ideaQuery]);
  const ideaTotal = sheets.groups.reduce((n, g) => n + g.items.length, 0);
  const ideaShown = visibleIdeaGroups.reduce((n, g) => n + g.items.length, 0);

  if (!trip) return <Navigate to="/" replace />;

  const { it, hotel, flight, flights, flightCost, stayCost, expCost, total, chosenItems } = trip;
  const g = it.guide;
  const place = it.route?.length ? it.route.map((s) => s.country ? `${s.city}, ${s.country}` : s.city).join(" → ") : routeName(req);
  const primaryPlace = cityName(req.destination) !== req.destination ? cityName(req.destination) : g?.name || req.destination;
  const perPerson = Math.round(total / req.travelers);
  const budget = req.budget;
  const over = budget != null && total > budget;
  const budgetPct = budget ? Math.min(100, (total / budget) * 100) : 0;
  const booked = booking && booking.status !== "cancelled";
  const pie = [
    { name: "Flights", value: flightCost, color: C.flight },
    { name: "Stay", value: stayCost, color: C.stay },
    ...(expCost > 0 ? [{ name: "Experiences (est.)", value: expCost, color: C.exp }] : []),
  ];
  const months = g ? g.months.map((score, i) => ({ month: MONTHS[i], score, trip: g.timing.trip_months.includes(i + 1) })) : [];
  const counts = chosenItems.reduce((m, i) => ({ ...m, [i.day]: (m[i.day] || 0) + 1 }), {});
  const routeDealCount = Object.values(dealsByDay).reduce((n, list) => n + list.length, 0);
  const routePath = (it.route || []).filter((s) => s.lat != null && s.lng != null);
  const routePins = [
    ...routePath.map((s, i) => ({ id: `route-${s.code}-${i}`, lat: s.lat, lng: s.lng, kind: "sight", label: String(i + 1), title: `${s.city}${s.country ? `, ${s.country}` : ""}`, color: "#f5c76a" })),
    ...(trip.staySegments || []).filter((s) => s.hotel?.lat != null).map((s) => ({ id: `stay-${s.destination}`, lat: s.hotel.lat, lng: s.hotel.lng, kind: "hotel", label: "Stay", title: `${s.hotel.name} · ${cityName(s.destination)}`, color: "#2dd4bf" })),
  ];

  return (
    <div className="wrap page trip-page">
      <header className="trip-top">
        <Photo k={g?.hero} src={g?.hero_url} info={g?.hero_credit} className="trip-top-photo" alt="" />
        <div className="trip-top-body">
          <div className="eyebrow">Your trip</div>
          <h1 className="h2">{savedTrip?.name || place}</h1>
          <p className="muted trip-top-meta">
            {savedTrip?.name ? `${place} · ` : ""}{shortDate(req.start_date)} – {shortDate(req.end_date)} · {nights} nights
          </p>
          {(req.destinations?.length || 0) > 1 && (
            <div className="route-mini" aria-label="Trip route">
              {req.destinations.map((code, i) => <span key={code}>{i > 0 && <em>→</em>}{cityName(code)}</span>)}
            </div>
          )}
          {trip.staySegments?.length > 1 && (
            <div className="stay-mini" aria-label="Stay allocation">
              {trip.staySegments.map((s) => <span key={s.destination}>{cityName(s.destination)}: Days {s.start_day}-{s.end_day}, {s.hotel.name}</span>)}
            </div>
          )}
          <div className="trip-top-chips">
            <Link to="/book" className={`tag ${booked ? "booked" : ""}`}>{booked ? `✓ Booked · ${booking.reference}` : "Not booked yet"}</Link>
            <span className="tag">{money(total)} · {money(perPerson)} pp</span>
            {budget != null && <span className={`tag ${over ? "" : "hit"}`}>{over ? `${money(total - budget)} over budget` : `${money(budget - total)} under budget`}</span>}
            <button type="button" className="tag tag-btn" onClick={() => setLikesOpen(true)} title="What the trip, ideas and deals are tuned to">
              ❤️ {req.interests.length ? req.interests.slice(0, 2).map((k) => TAG_LABEL[k] || k).join(", ") + (req.interests.length > 2 ? ` +${req.interests.length - 2}` : "") : "No interests set"} · edit
            </button>
            <button type="button" className="tag tag-btn" onClick={() => setTravelersOpen(true)} title="Change how many are going">
              👥 {req.travelers} traveler{req.travelers > 1 ? "s" : ""} · change
            </button>
            <button type="button" className="tag tag-btn" onClick={() => setFlightsOpen(true)} title="Compare and change your flight">
              ✈️ {flight.price_source === "estimate" ? connectionText(flight) : `${flight.airline} · ${connectionText(flight).split(" · ")[0]}`} · change
            </button>
          </div>
        </div>
        <div className="trip-top-actions">
          <Link to="/" className="btn ghost sm">✎ Change</Link>
          <button type="button" className="btn ghost sm" onClick={() => { resetSearch(); navigate("/"); }}>↺ New</button>
        </div>
      </header>

      <CareCard phase={phase} place={place} onDay={scrollToDay} onAdd={sheets.openAdd} weather={weather} say={sheets.say} onTickets={() => setTicketsOpen(true)} />

      <nav className="daystrip" ref={stripRef} aria-label="Jump to a day">
        {Array.from({ length: nights + 1 }, (_, i) => i + 1).map((d) => {
          const date = new Date(dayDate(req.start_date, d) + "T00:00:00");
          return (
            <button key={d} data-day={d} type="button" className={`daystrip-day ${phase.phase === "during" && phase.day === d ? "is-today" : ""}`} aria-pressed={activeDay === d} onClick={() => scrollToDay(d)}>
              <span className="daystrip-w">{date.toLocaleDateString("en-GB", { weekday: "short" })}</span>
              <b>{date.getDate()}</b>
              <span className="daystrip-n">{counts[d] ? "•".repeat(Math.min(4, counts[d])) : d === nights + 1 ? "✈" : " "}</span>
            </button>
          );
        })}
      </nav>

      {routePins.length > 1 && (
        <section className="card route-map-card">
          <div className="route-map-head">
            <div>
              <span className="tag-strong">Route map</span>
              <b>{place}</b>
            </div>
            <Link to="/explore" className="btn ghost sm">Explore route ideas</Link>
          </div>
          <MapView center={[routePath[0]?.lat || g?.center?.[0] || 0, routePath[0]?.lng || g?.center?.[1] || 0]} pins={routePins} path={routePath} height={320} />
          <p className="fine">Gold pins are route stops in order. Stay pins show where each hotel segment is based.</p>
        </section>
      )}

      <TripTimeline phase={phase} dealsByDay={dealsByDay} eventsByDate={eventsByDate} sheets={sheets} onChangeFlight={() => setFlightsOpen(true)} weather={weather} />
      <p className="fine trip-deals-note">
        {routeDealCount > 0 ? `${DISCLOSURE} ` : "No partner deals along your route yet. We'll show them here as businesses add them. "}
        <Link to="/deals">All deals in {primaryPlace} →</Link>
      </p>

      {sheets.groups.length > 0 && (
        <details className="fold card ideas-fold" open={chosenItems.length === 0}>
          <summary><b>Ideas for your trip</b><span className="muted">Tap + Add, then pick the day and time</span></summary>
          <div className="fold-body plan-suggestions">
            <IdeaSearch value={ideaQuery} onChange={setIdeaQuery} groups={sheets.groups} total={ideaTotal} shown={ideaShown} />
            {visibleIdeaGroups.length === 0 && <p className="muted">No ideas match that search. Try another word, like beach, food, museum or rooftop.</p>}
            {visibleIdeaGroups.map((grp) => (
              <div key={grp.key} className="suggest-group">
                <span className="tag-strong">{grp.label}</span>
                <div className="idea-grid">
                  {grp.items.map((item) => <IdeaRow key={item.key} item={item} onAdd={() => sheets.openWhen(item, "add", Math.min(activeDay, nights))} />)}
                </div>
              </div>
            ))}
          </div>
        </details>
      )}

      <h2 className="trip-details-h">Trip details</h2>
      <div className="trip-details">
        <Fold title="Your stay" hint={`${hotel.name}${qualityLabel(hotel) ? ` · ${qualityLabel(hotel)}` : ""}`}>
          <StayDetail hotel={hotel} interests={req.interests} nights={nights} />
          <Link to="/stays" className="btn ghost sm">Compare other stays</Link>
        </Fold>

        <Fold title="Costs and budget" hint={`${money(total)} in total`}>
          <div className="costs">
            <div className="donut">
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={pie} dataKey="value" innerRadius={64} outerRadius={94} paddingAngle={3} stroke="none">
                    {pie.map((p) => <Cell key={p.name} fill={p.color} />)}
                  </Pie>
                  <Tooltip formatter={(v) => money(v)} contentStyle={{ background: "#0d1826", border: "1px solid #24364d", borderRadius: 10 }} itemStyle={{ color: "#e8eef6" }} />
                </PieChart>
              </ResponsiveContainer>
              <div className="donut-center"><b>{money(total)}</b><span>total</span></div>
            </div>
            <div>
              <ul className="legend-list">
                {pie.map((p) => (
                  <li key={p.name}><i style={{ background: p.color }} /><span>{p.name}</span><b>{money(p.value)}</b><em>{Math.round((p.value / total) * 100)}%</em></li>
                ))}
              </ul>
              {(() => {
                // Booked partner deals are separate purchases, often in another currency: listed, never added to the total.
                const mine = dealBooking.forTrip(savedTrip?.id);
                if (!mine.length) return null;
                const sum = (pay) => Object.entries(mine.filter((b) => (b.pay || "venue") === pay).reduce((m, b) => ({ ...m, [b.currency]: (m[b.currency] || 0) + b.total }), {}))
                  .map(([cur, v]) => money(v, cur)).join(" + ");
                return (
                  <div className="deal-costs">
                    <span className="tag-strong">Booked deals</span>
                    {mine.map((b) => (
                      <div key={b.reference} className="deal-cost-row">
                        <span>{b.deal.title} · Day {b.day}</span>
                        <b>{money(b.total, b.currency)}</b>
                        <em>{(b.pay || "venue") === "now" ? "paid" : "pay there"}</em>
                      </div>
                    ))}
                    {sum("venue") && <p className="fine">To pay at the places: {sum("venue")}.</p>}
                    {sum("now") && <p className="fine">Already paid in the app (demo): {sum("now")}.</p>}
                  </div>
                );
              })()}
              {budget != null && (
                <div className="budget-line">
                  <span>Budget {money(budget)}</span>
                  <div className="meter"><i className={over ? "bad" : ""} style={{ width: `${budgetPct}%` }} /></div>
                </div>
              )}
              {(flight.price_source === "estimate" || hotel.price_source === "estimate") && (
                <p className="fine">Flight and stay prices are estimates from distance, star class and season, not quotes.</p>
              )}
            </div>
          </div>
        </Fold>

        {it.packages?.length > 0 && (
          <Fold title="Flights and packages" hint={`${flights.length} flights · ${it.packages.length} flight + stay packages`}>
            <div className="pkg-flight">
              <div>
                <span className="tag-strong">Your flight</span>
                <b>{flight.price_source === "estimate" ? "Typical fare" : flight.airline} · {connectionText(flight)} · {duration(flight.duration_minutes)}</b>
                <span className="muted">{money(flight.total_price)} for everyone <SourceBadge mode={flight.price_source} /></span>
              </div>
              <button type="button" className="btn ghost sm" onClick={() => setFlightsOpen(true)}>Compare all {flights.length} flights</button>
            </div>
            <p className="muted fine">A package is one flight with one stay, priced together. Switching changes both at once; you can still change either on its own afterwards.</p>
            <div className="packages">
              {it.packages.map((p) => {
                const mine = p.flight.id === flight.id && p.hotel.id === hotel.id;
                const diff = Math.round(p.total_cost - (flightCost + stayCost));
                return (
                <div key={p.flight.id + p.hotel.id} className={`pkg ${mine ? "best" : ""}`}>
                  <div className="pkg-labels">{p.labels.map((l) => <span key={l} className="badge gold">{l}</span>)}</div>
                  <div className="pkg-total">{money(p.total_cost)}</div>
                  <div className="pkg-delta">{mine ? "Your flight and stay now" : diff === 0 ? "Same price as your flight and stay" : `${money(Math.abs(diff))} ${diff < 0 ? "less" : "more"} than your flight and stay`}</div>
                  <ul className="pkg-lines">
                    <li><span>Flight</span><b>{p.flight.stops === 0 ? "Direct" : `${p.flight.stops} stop${p.flight.stops > 1 ? "s" : ""}`} · {duration(p.flight.duration_minutes)}</b><em>{money(p.flight.total_price)} <SourceBadge mode={p.price_sources.flight} /></em></li>
                    <li><span>Stay</span><b>{p.hotel.name}{qualityLabel(p.hotel) ? ` · ${qualityLabel(p.hotel)}` : ""}</b><em>{money(p.hotel.price_per_night)}/night <SourceBadge mode={p.price_sources.hotel} /></em></li>
                  </ul>
                  <p className="muted">{p.blurb}</p>
                  {mine ? <span className="flight-mine">✓ Your trip now</span> : (
                    <button type="button" className="btn primary sm" onClick={() => { choosePackage(p.flight.id, p.hotel.id); sheets.say(`Switched to the ${p.labels[0]} package${diff ? `: ${money(Math.abs(diff))} ${diff < 0 ? "less" : "more"}` : ""}`); }}>
                      Switch to this package
                    </button>
                  )}
                </div>
                );
              })}
            </div>
          </Fold>
        )}

        <Fold title="Why this trip" hint="The agent's reasoning, pros and cons">
          {it.ai?.summary && (
            <div className="ai-card-inline">
              <span className="src-badge muted" title="Written by an OpenAI model using only the facts on this page.">✨ {it.ai.model} · grounded in the data</span>
              <p className="ai-text">{it.ai.summary}</p>
            </div>
          )}
          <div className="pc2">
            <div className="pc2-col"><h3 className="ok">What you gain</h3><ul className="pros">{it.pros.map((t) => <li key={t}>{t}</li>)}</ul></div>
            <div className="pc2-col"><h3 className="no">What to weigh up</h3><ul className="cons">{it.cons.map((t) => <li key={t}>{t}</li>)}</ul></div>
          </div>
          <div className="why-strip">
            <span className="tag-strong">Why the agent chose this</span>
            {it.rationale.map((r) => <p key={r}>{r}</p>)}
            {!trip.isBest && <p className="fine">You picked a different stay from the agent's best match, so totals differ from the analysis above.</p>}
          </div>
        </Fold>

        {g && (
          <Fold title="Best time to go" hint={`Your dates: ${g.timing.verdict}`}>
            <div className="season-grid">
              <div>
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={months} margin={{ top: 8, right: 0, left: 0, bottom: 0 }}>
                    <XAxis dataKey="month" tickLine={false} axisLine={false} tick={{ fill: "#8ea2b9", fontSize: 12 }} />
                    <Tooltip cursor={{ fill: "rgba(255,255,255,.04)" }} formatter={(v) => [`${v} of 5`, "Suitability"]} contentStyle={{ background: "#0d1826", border: "1px solid #24364d", borderRadius: 10 }} itemStyle={{ color: "#e8eef6" }} />
                    <Bar dataKey="score" radius={[7, 7, 0, 0]}>
                      {months.map((m) => <Cell key={m.month} fill={m.trip ? "#f5c76a" : "#2dd4bf"} fillOpacity={m.trip ? 1 : 0.28 + m.score * 0.14} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <div className="scale"><i className="gold" /> Your trip <i className="teal" /> Other months, taller means better</div>
              </div>
              <div className="season-facts">
                <div className="fact"><span>Ultimate time to go</span><b>{g.timing.best_windows}</b></div>
                <div className="fact"><span>Best avoided</span><b>{g.timing.avoid_windows || "None"}</b></div>
                {g.timing.suggestion && <div className="callout"><b>Tip:</b> {g.timing.suggestion}</div>}
                <p className="fine">{g.season_note}</p>
              </div>
            </div>
          </Fold>
        )}

        {readback && (
          <Fold title="How I read your request" hint="What came from your words, and what I assumed" open>
            {readback.prompt && <p className="quote">“{readback.prompt}”{readback.photo ? " + your photo" : ""}</p>}
            <div className="readback-cols">
              <div><span className="tag-strong">From your words</span><ul>{readbackLines(readback.said, req, cityName, routeName, true).map((l) => <li key={l}>{l}</li>)}</ul></div>
              <div><span className="tag-strong">Not mentioned, so I assumed</span><ul>{readbackLines(readback.said, req, cityName, routeName, false).map((l) => <li key={l}>{l}</li>)}</ul></div>
            </div>
            {profile && (
              <div className="profile-inline">
                <div className="card-head"><span className="tag-strong">Your travel profile</span><button className="link-btn plain" onClick={forgetProfile}>Forget my profile</button></div>
                {profile.summary && <p className="ai-text">{profile.summary}</p>}
                <div className="chips">
                  {profile.keywords.map((k) => <span key={k} className="tag hit">{k}</span>)}
                  {profile.place_types.map((k) => <span key={k} className="tag">{PLACE_TYPE_LABEL[k] || k}</span>)}
                </div>
              </div>
            )}
          </Fold>
        )}

        <Fold title="Name and saving" hint={savedTrip ? "Saved to My trips" : "Not saved"}>
          <SaveTripBar />
          <AccountPanel compact />
        </Fold>

        <Fold title="Where this data comes from" hint="Live, estimated or demo, for every number">
          <ul className="sources">
            {it.data_sources.map((s) => (
              <li key={s.key}><div className="sources-l"><b>{s.label}</b><SourceBadge mode={s.mode} /></div><p>{s.detail}</p></li>
            ))}
          </ul>
        </Fold>
      </div>

      <PlanBar say={sheets.say} onUpdateTickets={() => setTicketsOpen(true)} />
      <TicketsSheet open={ticketsOpen} onClose={() => setTicketsOpen(false)} say={sheets.say} />
      <FlightPicker open={flightsOpen} onClose={() => setFlightsOpen(false)} say={sheets.say} />
      <TravelersSheet open={travelersOpen} onClose={() => setTravelersOpen(false)} say={sheets.say} />
      <InterestsSheet open={likesOpen} onClose={() => setLikesOpen(false)} say={sheets.say} />
      {sheets.ui}
    </div>
  );
}
