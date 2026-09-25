import { useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { useTrip } from "../state/TripContext.jsx";
import { fetchDeals, fetchEvents } from "../api";
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
import { IdeaRow, usePlanSheets } from "../components/PlanSheets.jsx";
import FlightPicker, { connectionText } from "../components/FlightPicker.jsx";
import TravelersSheet from "../components/TravelersSheet.jsx";
import InterestsSheet from "../components/InterestsSheet.jsx";

const C = { flight: "#818cf8", stay: "#2dd4bf", exp: "#f5c76a" };

/** One line per part of the trip, split by whether the person's words gave it or the form did. */
function readbackLines(said, req, cityName, fromWords) {
  const has = (k) => said.includes(k);
  const parts = [
    ["origin", `Flying from ${cityName(req.origin)}`],
    ["destination", `Going to ${cityName(req.destination)}`],
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
  const { trip, cityName, profile, forgetProfile, config, resetSearch, readback, booking, savedTrip, destinations, choosePackage } = useTrip();
  const [flightsOpen, setFlightsOpen] = useState(false);
  const [travelersOpen, setTravelersOpen] = useState(false);
  const [likesOpen, setLikesOpen] = useState(false);
  const navigate = useNavigate();
  const [activeDay, setActiveDay] = useState(1);
  const [deals, setDeals] = useState([]);
  const [events, setEvents] = useState([]);
  const stripRef = useRef(null);

  const scrollToDay = (d) => {
    setActiveDay(d);
    const el = document.getElementById(`day-${d}`);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    el.classList.remove("flash");
    void el.offsetWidth; // restart the highlight animation
    el.classList.add("flash");
  };
  const sheets = usePlanSheets({ onShowDay: scrollToDay });

  const req = trip?.req;
  const nights = trip?.it.nights || 0;
  const phase = useMemo(() => (req ? tripPhase(req, nights) : null), [req, nights]);

  // Partner deals and events for the trip's city and dates, placed on the days whose route they lie along.
  useEffect(() => {
    if (!req) return undefined;
    let live = true;
    fetchDeals({ dest: req.destination, start: req.start_date, end: req.end_date, interests: req.interests.join(","), place_types: (req.place_types || []).join(",") })
      .then((r) => live && setDeals(r.deals || []))
      .catch(() => live && setDeals([]));
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
      centre: destinations.find((x) => x.code === req.destination), pinDay: phase?.phase === "during" ? phase.day : null,
    });
  }, [deals, trip, nights, req, phase, destinations]);
  const eventsByDate = useMemo(() => events.reduce((m, e) => ({ ...m, [e.date]: [...(m[e.date] || []), e] }), {}), [events]);

  if (!trip) return <Navigate to="/" replace />;

  const { it, hotel, flight, flights, flightCost, stayCost, expCost, total, chosenItems } = trip;
  const g = it.guide;
  const place = cityName(req.destination) !== req.destination ? cityName(req.destination) : g?.name || req.destination;
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

      <CareCard phase={phase} place={place} onDay={scrollToDay} onAdd={sheets.openAdd} />

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

      <TripTimeline phase={phase} dealsByDay={dealsByDay} eventsByDate={eventsByDate} sheets={sheets} onChangeFlight={() => setFlightsOpen(true)} />
      <p className="fine trip-deals-note">
        {routeDealCount > 0 ? `${DISCLOSURE} ` : "No partner deals along your route yet. We'll show them here as businesses add them. "}
        <Link to="/deals">All deals in {place} →</Link>
      </p>

      {sheets.groups.length > 0 && (
        <details className="fold card ideas-fold" open={chosenItems.length === 0}>
          <summary><b>Ideas for your trip</b><span className="muted">Tap + Add, then pick the day and time</span></summary>
          <div className="fold-body plan-suggestions">
            {sheets.groups.map((grp) => (
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
          <Fold title="How I read your request" hint="What came from your words, and what I assumed">
            {readback.prompt && <p className="quote">“{readback.prompt}”{readback.photo ? " + your photo" : ""}</p>}
            <div className="readback-cols">
              <div><span className="tag-strong">From your words</span><ul>{readbackLines(readback.said, req, cityName, true).map((l) => <li key={l}>{l}</li>)}</ul></div>
              <div><span className="tag-strong">Not mentioned, so I assumed</span><ul>{readbackLines(readback.said, req, cityName, false).map((l) => <li key={l}>{l}</li>)}</ul></div>
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
        </Fold>

        <Fold title="Where this data comes from" hint="Live, estimated or demo, for every number">
          <ul className="sources">
            {it.data_sources.map((s) => (
              <li key={s.key}><div className="sources-l"><b>{s.label}</b><SourceBadge mode={s.mode} /></div><p>{s.detail}</p></li>
            ))}
          </ul>
        </Fold>
      </div>

      <PlanBar say={sheets.say} />
      <FlightPicker open={flightsOpen} onClose={() => setFlightsOpen(false)} say={sheets.say} />
      <TravelersSheet open={travelersOpen} onClose={() => setTravelersOpen(false)} say={sheets.say} />
      <InterestsSheet open={likesOpen} onClose={() => setLikesOpen(false)} say={sheets.say} />
      {sheets.ui}
    </div>
  );
}
