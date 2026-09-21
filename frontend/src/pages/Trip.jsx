import { motion } from "framer-motion";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { useTrip } from "../state/TripContext.jsx";
import { DealsGrid, DISCLOSURE, EventsBlock } from "../components/DealsSection.jsx";
import { TAG_LABEL } from "../lib/constants";
import { MONTHS, duration, longDate, money, shortDate } from "../lib/format";
import { qualityLabel, stayPhotos } from "../lib/stay";
import { PLACE_TYPE_LABEL } from "../lib/profile";
import CountUp from "../components/CountUp.jsx";
import Photo from "../components/Photo.jsx";
import SourceBadge from "../components/SourceBadge.jsx";

const C = { flight: "#818cf8", stay: "#2dd4bf", exp: "#f5c76a" };

function addDays(iso, n) {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

const rise = (i = 0) => ({ initial: { opacity: 0, y: 22 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true, margin: "-40px" }, transition: { delay: i * 0.06, duration: 0.5 } });

/** Photo props for a guide item: a bundled key, or a live Wikimedia URL with its credit. */
const itemPhoto = (i) => ({ k: i.photo, src: i.photo_url, info: i.photo_credit });

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

export default function Trip() {
  const { trip, cityName, profile, forgetProfile, config, resetSearch, readback } = useTrip();
  const navigate = useNavigate();
  if (!trip) return <Navigate to="/" replace />;

  const { it, req, hotel, flightCost, stayCost, expCost, total, chosenItems } = trip;
  const g = it.guide;
  const flight = it.flight;
  const place = cityName(req.destination) !== req.destination ? cityName(req.destination) : g?.name || req.destination;
  const perPerson = Math.round(total / req.travelers);
  const budget = req.budget;
  const over = budget != null && total > budget;
  const budgetPct = budget ? Math.min(100, (total / budget) * 100) : 0;
  const quality = qualityLabel(hotel);

  const pie = [
    { name: "Flights", value: flightCost, color: C.flight },
    { name: "Stay", value: stayCost, color: C.stay },
    ...(expCost > 0 ? [{ name: "Experiences (est.)", value: expCost, color: C.exp }] : []),
  ];

  // Spread the chosen experiences across the free days between arrival and departure.
  const spacing = Math.max(1, Math.floor((it.nights - 2) / Math.max(1, chosenItems.length)));
  const stopsText = flight.stops === 0 ? "Direct" : `${flight.stops} stop${flight.stops > 1 ? "s" : ""}`;
  const events = [
    {
      day: 1, kind: "flight", title: `Fly ${cityName(req.origin)} → ${cityName(req.destination)}`,
      sub: [flight.price_source === "estimate" ? `Typical ${stopsText.toLowerCase()} fare` : `${flight.airline} · ${stopsText}`, duration(flight.duration_minutes), flight.depart_time && `departs ${flight.depart_time}`].filter(Boolean).join(" · "),
    },
    { day: 1, kind: "stay", title: `Check in at ${hotel.name}`, sub: `${[quality, `${money(hotel.price_per_night)} per night`].filter(Boolean).join(" · ")}`, photo: stayPhotos(hotel)[0] },
    ...chosenItems.map((item, i) => ({
      day: Math.min(it.nights, 2 + i * spacing),
      kind: "exp",
      title: item.name,
      sub: [item.duration, item.cost ? `about ${money(item.cost)} pp` : item.cost === 0 ? "free" : null].filter(Boolean).join(" · ") || item.why,
      photoProps: itemPhoto(item),
    })),
    { day: it.nights + 1, kind: "flight", title: `Fly home ${cityName(req.destination)} → ${cityName(req.origin)}`, sub: "Return flight included in your fare" },
  ].sort((a, b) => a.day - b.day);

  const months = g
    ? g.months.map((score, i) => ({ month: MONTHS[i], score, trip: g.timing.trip_months.includes(i + 1) }))
    : [];

  return (
    <>
      <section className="trip-hero">
        <Photo k={g?.hero} src={g?.hero_url} info={g?.hero_credit} className="trip-hero-bg" credit />
        <div className="trip-hero-scrim" />
        <div className="wrap trip-hero-inner">
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}>
            <div className="eyebrow">Your trip</div>
            <h1>{place}</h1>
            <p className="meta">
              {shortDate(req.start_date)} – {shortDate(req.end_date)} · {it.nights} nights · {req.travelers} traveler{req.travelers > 1 ? "s" : ""}
              {g && <span className={`verdict ${g.timing.verdict}`}>Season: {g.timing.verdict}</span>}
            </p>
            <div className="hero-actions">
              <Link to="/" className="btn ghost sm">✎ Change this search</Link>
              <button className="btn primary sm" onClick={() => { resetSearch(); navigate("/"); }}>↺ Start a new search</button>
            </div>
          </motion.div>
        </div>
      </section>

      <div className="wrap trip-body">
        <motion.section className="kpis glass" {...rise()}>
          <div className="kpi big">
            <span className="kpi-l">Trip total</span>
            <span className="kpi-v"><CountUp value={total} /></span>
            <span className="kpi-s">{money(perPerson)} per person</span>
          </div>
          <div className="kpi">
            <span className="kpi-l">Budget</span>
            {budget ? (
              <>
                <span className={`kpi-v sm ${over ? "bad" : "ok"}`}>{over ? `${money(total - budget)} over` : `${money(budget - total)} left`}</span>
                <div className="meter"><i className={over ? "bad" : ""} style={{ width: `${budgetPct}%` }} /></div>
              </>
            ) : (
              <span className="kpi-v sm">No limit set</span>
            )}
          </div>
          <div className="kpi">
            <span className="kpi-l">Stay</span>
            <span className="kpi-v sm">{hotel.name}</span>
            <span className="kpi-s">{trip.isBest ? "Agent's best match" : "Your choice"} · <Link to="/stays">change</Link></span>
          </div>
          <div className="kpi">
            <span className="kpi-l">Experiences</span>
            <span className="kpi-v sm">{chosenItems.length} planned</span>
            <span className="kpi-s">{expCost ? `${money(expCost)} est.` : "prices vary"} · <Link to="/explore">edit</Link></span>
          </div>
        </motion.section>

        {it.ai?.summary && (
          <motion.section className="card pad ai-card" {...rise()}>
            <div className="card-head">
              <h2 className="card-title">✨ Your AI trip summary</h2>
              <span className="src-badge muted" title="Written by an OpenAI model using only the facts on this page. Any text containing a number not in those facts is discarded.">
                {it.ai.model} · grounded in the data below
              </span>
            </div>
            <p className="ai-text">{it.ai.summary}</p>
          </motion.section>
        )}

        {readback && (
          <motion.section className="card pad readback" {...rise()}>
            <h2 className="card-title">How I read your request</h2>
            {readback.prompt && <p className="quote">“{readback.prompt}”{readback.photo ? " + your photo" : ""}</p>}
            <div className="readback-cols">
              <div>
                <span className="tag-strong">From your words</span>
                <ul>{readbackLines(readback.said, req, cityName, true).map((l) => <li key={l}>{l}</li>)}</ul>
              </div>
              <div>
                <span className="tag-strong">Not mentioned, so I assumed</span>
                <ul>{readbackLines(readback.said, req, cityName, false).map((l) => <li key={l}>{l}</li>)}</ul>
              </div>
            </div>
            <p className="fine">Not right? <Link to="/">Describe it again</Link>, or plan it with the form instead.</p>
          </motion.section>
        )}

        {profile && readback && (
          <motion.section className="card pad profile-card" {...rise()}>
            <div className="card-head">
              <h2 className="card-title">Your travel profile</h2>
              <button className="link-btn plain" onClick={forgetProfile}>Forget my profile</button>
            </div>
            {profile.summary && <p className="ai-text">{profile.summary}</p>}
            <div className="chips">
              {profile.keywords.map((k) => <span key={k} className="tag hit">{k}</span>)}
              {profile.vibe && <span className="tag">Vibe: {profile.vibe}</span>}
              {profile.pace && <span className="tag">Pace: {profile.pace}</span>}
              {profile.budget_style && <span className="tag">Budget: {profile.budget_style}</span>}
              {profile.place_types.map((k) => <span key={k} className="tag">{PLACE_TYPE_LABEL[k] || k}</span>)}
            </div>
            <p className="fine">Built from what you wrote or showed us. It is stored only in this browser, and it shapes the places we search for.</p>
          </motion.section>
        )}

        {it.packages?.length > 0 && (
          <motion.section className="card pad" {...rise()}>
            <h2 className="card-title">Compare your options</h2>
            <div className="packages">
              {it.packages.map((p) => (
                <div key={p.flight.id + p.hotel.id} className={`pkg ${p.labels.includes("Best match") ? "best" : ""}`}>
                  <div className="pkg-labels">{p.labels.map((l) => <span key={l} className="badge gold">{l}</span>)}</div>
                  <div className="pkg-total">{money(p.total_cost)}</div>
                  <div className="pkg-delta">
                    {p.vs_best === 0 ? "The agent's pick" : `${money(Math.abs(p.vs_best))} ${p.vs_best < 0 ? "cheaper" : "more"} than the best match`}
                  </div>
                  <ul className="pkg-lines">
                    <li>
                      <span>Flight</span>
                      <b>{p.flight.stops === 0 ? "Direct" : `${p.flight.stops} stop${p.flight.stops > 1 ? "s" : ""}`} · {duration(p.flight.duration_minutes)}</b>
                      <em>{money(p.flight.total_price)} <SourceBadge mode={p.price_sources.flight} /></em>
                    </li>
                    <li>
                      <span>Stay</span>
                      <b>{p.hotel.name}{qualityLabel(p.hotel) ? ` · ${qualityLabel(p.hotel)}` : ""}</b>
                      <em>{money(p.hotel.price_per_night)}/night <SourceBadge mode={p.price_sources.hotel} /></em>
                    </li>
                  </ul>
                  <p className="muted">{p.blurb}</p>
                </div>
              ))}
            </div>
            <p className="fine">Compared across the flights and stays found for your dates. Free data has no price comparison across booking sites, so prices marked Estimate are modelled; add Amadeus keys for real offers.</p>
          </motion.section>
        )}

        {(req.interests.includes("nightlife") || (readback && profile?.place_types?.some((t) => t === "nightclub" || t === "pub"))) && (
          <motion.section className="card pad tonight-cta" {...rise()}>
            <div>
              <h2 className="card-title">🌙 Nightlife in {place}</h2>
              <p className="muted">See the best clubs and bars that are open on any night of your trip, with photos, hours and any live deal.</p>
            </div>
            <Link to="/tonight" className="btn primary">Find the best clubs tonight</Link>
          </motion.section>
        )}

        {it.partner_deals?.length > 0 && (
          <motion.section className="card pad" {...rise()}>
            <div className="card-head">
              <h2 className="card-title">Partner deals for your trip</h2>
              <Link to="/deals" className="btn ghost sm">See all deals</Link>
            </div>
            <DealsGrid deals={it.partner_deals} />
            <p className="fine">{DISCLOSURE}</p>
          </motion.section>
        )}

        {config.ticketmaster && (
          <motion.section className="card pad" {...rise()}>
            <h2 className="card-title">What is on during your trip</h2>
            <EventsBlock dest={req.destination} start={req.start_date} end={req.end_date} enabled />
          </motion.section>
        )}

        <div className="two-col">
          <motion.section className="card pad" {...rise(1)}>
            <h2 className="card-title">Where the money goes</h2>
            <div className="donut">
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie data={pie} dataKey="value" innerRadius={72} outerRadius={104} paddingAngle={3} stroke="none" isAnimationActive>
                    {pie.map((p) => <Cell key={p.name} fill={p.color} />)}
                  </Pie>
                  <Tooltip formatter={(v) => money(v)} contentStyle={{ background: "#0d1826", border: "1px solid #24364d", borderRadius: 10 }} itemStyle={{ color: "#e8eef6" }} />
                </PieChart>
              </ResponsiveContainer>
              <div className="donut-center"><b>{money(total)}</b><span>total</span></div>
            </div>
            <ul className="legend-list">
              {pie.map((p) => (
                <li key={p.name}>
                  <i style={{ background: p.color }} />
                  <span>{p.name}</span>
                  <b>{money(p.value)}</b>
                  <em>{Math.round((p.value / total) * 100)}%</em>
                </li>
              ))}
            </ul>
            {(flight.price_source === "estimate" || hotel.price_source === "estimate") && (
              <p className="fine">Flight and stay prices are estimates from distance, star class and season, not quotes. Add Amadeus keys for real offers.</p>
            )}
          </motion.section>

          <motion.section className="card pad" {...rise(2)}>
            <h2 className="card-title">Your itinerary</h2>
            <ol className="timeline">
              {events.map((e, i) => (
                <li key={i} className={`tl ${e.kind}`}>
                  <span className="tl-dot" />
                  <div className="tl-body">
                    <span className="tl-day">Day {e.day} · {longDate(addDays(req.start_date, e.day - 1))}</span>
                    <b>{e.title}</b>
                    <small>{e.sub}</small>
                  </div>
                  {e.photo && <Photo k={e.photo} className="tl-photo" />}
                  {e.photoProps && (e.photoProps.k || e.photoProps.src) && <Photo {...e.photoProps} className="tl-photo" />}
                </li>
              ))}
            </ol>
          </motion.section>
        </div>

        <motion.section className="card" {...rise()}>
          <div className="pc2">
            <div className="pc2-col">
              <h3 className="ok">What you gain</h3>
              <ul className="pros">{it.pros.map((t) => <li key={t}>{t}</li>)}</ul>
            </div>
            <div className="pc2-col">
              <h3 className="no">What to weigh up</h3>
              <ul className="cons">{it.cons.map((t) => <li key={t}>{t}</li>)}</ul>
            </div>
          </div>
          <p className="fine pc2-note">Pros and cons cover the flight and the agent's stay pick; experiences are extra.</p>
          <div className="why-strip">
            <span className="tag-strong">Why the agent chose this</span>
            {it.rationale.map((r) => <p key={r}>{r}</p>)}
            {!trip.isBest && <p className="fine">You picked a different stay from the agent's best match, so totals differ from the analysis above.</p>}
          </div>
        </motion.section>

        {g && (
          <motion.section className="card pad" {...rise()}>
            <div className="card-head">
              <h2 className="card-title">Best time to go</h2>
              <span className={`verdict ${g.timing.verdict}`}>Your dates: {g.timing.verdict}</span>
            </div>
            <div className="season-grid">
              <div>
                <ResponsiveContainer width="100%" height={190}>
                  <BarChart data={months} margin={{ top: 8, right: 0, left: 0, bottom: 0 }}>
                    <XAxis dataKey="month" tickLine={false} axisLine={false} tick={{ fill: "#8ea2b9", fontSize: 12 }} />
                    <Tooltip
                      cursor={{ fill: "rgba(255,255,255,.04)" }}
                      formatter={(v, _n, p) => {
                        const c = g.climate?.[MONTHS.indexOf(p.payload.month)];
                        return [c ? `${v} of 5 · highs ${c.tmax}°C · ${c.rain_mm} mm rain` : `${v} of 5`, "Suitability"];
                      }}
                      contentStyle={{ background: "#0d1826", border: "1px solid #24364d", borderRadius: 10 }}
                      itemStyle={{ color: "#e8eef6" }}
                    />
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
          </motion.section>
        )}

        {g && (
          <motion.section {...rise()}>
            <div className="section-head row">
              <h2>Don't miss</h2>
              <Link to="/explore" className="link-btn">See all on the map →</Link>
            </div>
            <div className="highlights">
              {[...g.places, ...g.adventures].sort((a, b) => b.matches.length - a.matches.length).filter((i) => i.photo || i.photo_url).slice(0, 4).map((i) => (
                <Link to="/explore" className="hl" key={i.name}>
                  <Photo {...itemPhoto(i)} className="hl-photo" />
                  <div className="hl-scrim" />
                  <div className="hl-body">
                    <b>{i.name}</b>
                    <span>{i.matches.length ? `Matches: ${i.matches.map((t) => TAG_LABEL[t] || t).join(", ")}` : i.why}</span>
                  </div>
                </Link>
              ))}
            </div>
          </motion.section>
        )}

        <motion.section className="card pad" {...rise()}>
          <h2 className="card-title">Where this data comes from</h2>
          <ul className="sources">
            {it.data_sources.map((s) => (
              <li key={s.key}>
                <div className="sources-l"><b>{s.label}</b><SourceBadge mode={s.mode} /></div>
                <p>{s.detail}</p>
              </li>
            ))}
          </ul>
          <p className="fine">Live sources are free public services (Open-Meteo, Wikipedia and Wikimedia Commons, OpenStreetMap). Prices marked Estimate are modelled, not quoted.</p>
        </motion.section>

        <div className="cta-row">
          <Link to="/stays" className="btn primary">Compare all stays</Link>
          <Link to="/explore" className="btn ghost">Explore places and food</Link>
        </div>
      </div>
    </>
  );
}
