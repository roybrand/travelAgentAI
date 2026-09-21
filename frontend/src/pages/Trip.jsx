import { motion } from "framer-motion";
import { Link, Navigate } from "react-router-dom";
import { Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { useTrip } from "../state/TripContext.jsx";
import { CITY_NAME, TAG_LABEL } from "../lib/constants";
import { MONTHS, duration, longDate, money, shortDate } from "../lib/format";
import CountUp from "../components/CountUp.jsx";
import Photo from "../components/Photo.jsx";

const C = { flight: "#818cf8", stay: "#2dd4bf", exp: "#f5c76a" };

function addDays(iso, n) {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

const rise = (i = 0) => ({ initial: { opacity: 0, y: 22 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true, margin: "-40px" }, transition: { delay: i * 0.06, duration: 0.5 } });

export default function Trip() {
  const { trip } = useTrip();
  if (!trip) return <Navigate to="/" replace />;

  const { it, req, hotel, flightCost, stayCost, expCost, total, chosenItems } = trip;
  const g = it.guide;
  const flight = it.flight;
  const place = CITY_NAME[req.destination.toUpperCase()] || g?.name || req.destination;
  const perPerson = Math.round(total / req.travelers);
  const budget = req.budget;
  const over = budget != null && total > budget;
  const budgetPct = budget ? Math.min(100, (total / budget) * 100) : 0;

  const pie = [
    { name: "Flights", value: flightCost, color: C.flight },
    { name: "Stay", value: stayCost, color: C.stay },
    ...(expCost > 0 ? [{ name: "Experiences (est.)", value: expCost, color: C.exp }] : []),
  ];

  // Spread the chosen experiences across the free days between arrival and departure.
  const spacing = Math.max(1, Math.floor((it.nights - 2) / Math.max(1, chosenItems.length)));
  const events = [
    { day: 1, kind: "flight", title: `Fly ${req.origin} → ${req.destination}`, sub: `${flight.airline} · ${flight.stops === 0 ? "Direct" : `${flight.stops} stop${flight.stops > 1 ? "s" : ""}`} · ${duration(flight.duration_minutes)} · departs ${flight.depart_time}` },
    { day: 1, kind: "stay", title: `Check in at ${hotel.name}`, sub: `${hotel.rating.toFixed(1)}★ · ${money(hotel.price_per_night)} per night`, photo: hotel.photos?.[0] },
    ...chosenItems.map((item, i) => ({
      day: Math.min(it.nights, 2 + i * spacing),
      kind: "exp",
      title: item.name,
      sub: `${item.duration || ""}${item.cost ? ` · about ${money(item.cost)} pp` : " · free"}`,
      photo: item.photo,
    })),
    { day: it.nights + 1, kind: "flight", title: `Fly home ${req.destination} → ${req.origin}`, sub: "Return flight included in your fare" },
  ].sort((a, b) => a.day - b.day);

  const months = g
    ? g.months.map((score, i) => ({ month: MONTHS[i], score, trip: g.timing.trip_months.includes(i + 1) }))
    : [];

  return (
    <>
      <section className="trip-hero">
        <Photo k={g?.hero} className="trip-hero-bg" credit />
        <div className="trip-hero-scrim" />
        <div className="wrap trip-hero-inner">
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}>
            <div className="eyebrow">Your trip</div>
            <h1>{place}</h1>
            <p className="meta">
              {shortDate(req.start_date)} – {shortDate(req.end_date)} · {it.nights} nights · {req.travelers} traveler{req.travelers > 1 ? "s" : ""}
              {g && <span className={`verdict ${g.timing.verdict}`}>Season: {g.timing.verdict}</span>}
            </p>
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
            <span className="kpi-l">{budget ? "Budget" : "Budget"}</span>
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
            <span className="kpi-s">{expCost ? `${money(expCost)} est.` : "none yet"} · <Link to="/explore">edit</Link></span>
          </div>
        </motion.section>

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
            {expCost > 0 && <p className="fine">Experience costs are rough per-person estimates for the activities you added.</p>}
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
                      formatter={(v) => [`${v} of 5`, "Suitability"]}
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
              {[...g.places, ...g.adventures].sort((a, b) => b.matches.length - a.matches.length).slice(0, 4).map((i) => (
                <Link to="/explore" className="hl" key={i.name}>
                  <Photo k={i.photo} className="hl-photo" />
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

        <div className="cta-row">
          <Link to="/stays" className="btn primary">Compare all stays</Link>
          <Link to="/explore" className="btn ghost">Explore places and deals</Link>
        </div>
      </div>
    </>
  );
}
