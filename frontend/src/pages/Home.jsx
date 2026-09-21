import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { useTrip } from "../state/TripContext.jsx";
import { INTERESTS, SHOWCASE } from "../lib/constants";
import { isoDate } from "../lib/format";
import Photo from "../components/Photo.jsx";
import PlanningOverlay from "../components/PlanningOverlay.jsx";

const FEATURES = [
  ["Ranked, not just listed", "Every flight and stay is scored on price, quality, your interests and budget fit, then combined into one best pick."],
  ["Pros and cons, in plain words", "See exactly what you gain and give up with each choice, based on the real numbers in your search."],
  ["The right time to go", "Your dates are scored against the destination's season, with a nudge when a better window exists."],
  ["Places, adventures, nearby deals", "Photos, a map, what it costs, and the best-value spots within walking distance."],
];

export default function Home() {
  const { form, setForm, plan, loading, error, setError } = useTrip();
  const navigate = useNavigate();
  const [slide, setSlide] = useState(0);
  const [formError, setFormError] = useState("");

  useEffect(() => {
    const t = setInterval(() => setSlide((s) => (s + 1) % SHOWCASE.length), 6500);
    return () => clearInterval(t);
  }, []);

  const set = (patch) => setForm((f) => ({ ...f, ...patch }));
  const toggleInterest = (k) =>
    set({ interests: form.interests.includes(k) ? form.interests.filter((x) => x !== k) : [...form.interests, k] });

  function validate(p) {
    if (!p.origin) return "Enter where you are flying from.";
    if (!p.destination) return "Choose a destination.";
    if (p.origin === p.destination) return "Origin and destination must differ.";
    if (!p.start_date || !p.end_date || p.end_date <= p.start_date) return "The return date must be after departure.";
    if (p.budget !== null && !(p.budget > 0)) return "Budget must be greater than zero.";
    return "";
  }

  async function submit(e) {
    e.preventDefault();
    const payload = {
      ...form,
      origin: form.origin.trim().toUpperCase(),
      destination: form.destination.trim().toUpperCase(),
      budget: form.budget === "" || form.budget == null ? null : Number(form.budget),
    };
    const msg = validate(payload);
    setFormError(msg);
    if (msg) return;
    setError("");
    if (await plan(payload)) navigate("/trip");
  }

  const chosen = SHOWCASE.find((s) => s.code === form.destination.trim().toUpperCase());
  const today = isoDate(new Date());

  return (
    <>
      <AnimatePresence>{loading && <PlanningOverlay photo={chosen?.photo || SHOWCASE[slide].photo} />}</AnimatePresence>

      <section className="hero">
        {SHOWCASE.map((s, i) => (
          <Photo key={s.code} k={s.photo} className={`hero-bg ${i === slide ? "on" : ""}`} credit={i === slide} />
        ))}
        <div className="hero-scrim" />
        <div className="wrap hero-inner">
          <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1, duration: 0.6 }}>
            <div className="eyebrow">AI travel agent</div>
            <h1>See it before <span>you book it.</span></h1>
            <p className="lede">
              Flights, stays and experiences, ranked by an AI agent and laid out with photos, maps and charts so
              the best choice is obvious at a glance.
            </p>
          </motion.div>

          <motion.form
            className="search glass"
            onSubmit={submit}
            noValidate
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25, duration: 0.6 }}
          >
            <div className="dest-grid" role="radiogroup" aria-label="Destination">
              {SHOWCASE.map((s) => (
                <button
                  type="button"
                  key={s.code}
                  role="radio"
                  aria-checked={chosen?.code === s.code}
                  className={`dest ${chosen?.code === s.code ? "on" : ""}`}
                  onClick={() => set({ destination: s.code })}
                >
                  <Photo k={s.photo} className="dest-photo" />
                  <span className="dest-name">
                    <b>{s.city}</b>
                    <small>{s.country}</small>
                  </span>
                </button>
              ))}
            </div>

            <div className="fields">
              <label className="field">
                <span>From</span>
                <input value={form.origin} onChange={(e) => set({ origin: e.target.value })} placeholder="City or code" maxLength={30} />
              </label>
              <label className="field">
                <span>To (or any other code)</span>
                <input value={form.destination} onChange={(e) => set({ destination: e.target.value })} placeholder="e.g. NAP" maxLength={30} />
              </label>
              <label className="field">
                <span>Depart</span>
                <input type="date" min={today} value={form.start_date} onChange={(e) => set({ start_date: e.target.value })} />
              </label>
              <label className="field">
                <span>Return</span>
                <input type="date" min={form.start_date} value={form.end_date} onChange={(e) => set({ end_date: e.target.value })} />
              </label>
              <label className="field">
                <span>Total budget (£)</span>
                <input type="number" min="1" step="50" value={form.budget ?? ""} onChange={(e) => set({ budget: e.target.value })} placeholder="No limit" />
              </label>
              <div className="field">
                <span>Travelers</span>
                <div className="stepper">
                  <button type="button" aria-label="Fewer travelers" onClick={() => set({ travelers: Math.max(1, form.travelers - 1) })}>−</button>
                  <output>{form.travelers}</output>
                  <button type="button" aria-label="More travelers" onClick={() => set({ travelers: Math.min(12, form.travelers + 1) })}>+</button>
                </div>
              </div>
            </div>

            <div className="field">
              <span>What matters to you</span>
              <div className="chips">
                {INTERESTS.map(([k, label]) => (
                  <button type="button" key={k} className="chip" aria-pressed={form.interests.includes(k)} onClick={() => toggleInterest(k)}>
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {(formError || error) && <p className="err" role="alert">{formError || error}</p>}
            <button className="btn primary big" type="submit" disabled={loading}>
              {loading ? "Planning…" : "Plan my trip"}
            </button>
          </motion.form>
        </div>
      </section>

      <section className="wrap section">
        <div className="section-head">
          <h2>Four places, fully mapped</h2>
          <p>Pick a showcase destination for the full visual experience: photos, an interactive map and nearby deals.</p>
        </div>
        <div className="showcase">
          {SHOWCASE.map((s) => (
            <button
              key={s.code}
              className="showcard"
              onClick={() => {
                set({ destination: s.code });
                window.scrollTo({ top: 0, behavior: "smooth" });
              }}
            >
              <Photo k={s.photo} className="showcard-photo" credit />
              <div className="showcard-body">
                <b>{s.city}</b>
                <span>{s.tagline}</span>
              </div>
            </button>
          ))}
        </div>
      </section>

      <section className="wrap section">
        <div className="section-head">
          <h2>Built to make the decision easy</h2>
        </div>
        <div className="features">
          {FEATURES.map(([t, d], i) => (
            <div className="feature glass" key={t}>
              <span className="feature-n">{i + 1}</span>
              <h3>{t}</h3>
              <p>{d}</p>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
