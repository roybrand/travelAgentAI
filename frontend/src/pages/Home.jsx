import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { buildTrip } from "../api";
import { useTrip } from "../state/TripContext.jsx";
import { INTERESTS, SHOWCASE } from "../lib/constants";
import { isoDate } from "../lib/format";
import { PLACE_TYPE_LABEL, resizeImage } from "../lib/profile";
import DestSelect from "../components/DestSelect.jsx";
import Photo from "../components/Photo.jsx";
import PlanningOverlay from "../components/PlanningOverlay.jsx";

const FEATURES = [
  ["100 destinations, live data", "Europe, the Americas and Asia. Real weather, real sights and photos, real hotels and restaurants from free public sources."],
  ["Ranked, not just listed", "Every flight and stay is scored on price, quality, your interests and budget fit, then combined into one best pick."],
  ["Honest about what it knows", "Every price and data source is labelled: live, estimate or demo. Nothing is invented and passed off as real."],
  ["The right time to go", "Your dates are scored against real historical weather for the destination, with a nudge when a better window exists."],
];

export default function Home() {
  const { form, setForm, plan, loading, error, setError, config, destinations, profile, setProfile, forgetProfile } = useTrip();
  const navigate = useNavigate();
  const [slide, setSlide] = useState(0);
  const [formError, setFormError] = useState("");
  const [freeText, setFreeText] = useState("");
  const [parsing, setParsing] = useState(false);
  const [image, setImage] = useState(null);
  const fileRef = useRef(null);
  const [assumptions, setAssumptions] = useState([]);

  useEffect(() => {
    const t = setInterval(() => setSlide((s) => (s + 1) % SHOWCASE.length), 6500);
    return () => clearInterval(t);
  }, []);

  const set = (patch) => setForm((f) => ({ ...f, ...patch }));
  const toggleInterest = (k) =>
    set({ interests: form.interests.includes(k) ? form.interests.filter((x) => x !== k) : [...form.interests, k] });

  function validate(p) {
    if (!p.origin) return "Choose where you are flying from.";
    if (!p.destination) return "Choose a destination.";
    if (p.origin === p.destination) return "Origin and destination must differ.";
    if (!p.start_date || !p.end_date || p.end_date <= p.start_date) return "The return date must be after departure.";
    if (p.budget !== null && !(p.budget > 0)) return "Budget must be greater than zero.";
    return "";
  }

  async function submit(e) {
    e.preventDefault();
    const payload = { ...form, budget: form.budget === "" || form.budget == null ? null : Number(form.budget) };
    const msg = validate(payload);
    setFormError(msg);
    if (msg) return;
    setError("");
    if (await plan(payload)) navigate("/trip");
  }

  async function pickImage(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    try {
      setImage(await resizeImage(file));
      setFormError("");
    } catch (err) {
      setFormError(err.message);
    }
  }

  /** Prompt (and optional photo) -> trip fields + a traveler profile -> plan the whole trip. */
  async function build() {
    setParsing(true);
    setFormError("");
    setAssumptions([]);
    try {
      const { assumptions: notes = [], profile: prof, ...fields } = await buildTrip(freeText, image);
      const gotSomething = Object.keys(fields).length || prof?.place_types?.length || prof?.interests?.length;
      if (!gotSomething) throw new Error("I could not find any trip details in that. Try adding a place, or a photo of somewhere you like.");
      const merged = { ...form, ...fields, interests: prof?.interests?.length ? prof.interests : fields.interests || form.interests };
      setForm(merged);
      setAssumptions(notes);
      if (prof) setProfile(prof);
      const payload = {
        ...merged,
        budget: merged.budget === "" || merged.budget == null ? null : Number(merged.budget),
        place_types: prof?.place_types ?? [],
      };
      const msg = validate(payload);
      if (msg) throw new Error(`${msg} The form below has what I understood, so you can adjust it.`);
      setParsing(false);
      if (await plan(payload)) navigate("/trip");
    } catch (e) {
      setFormError(e.message);
    } finally {
      setParsing(false);
    }
  }

  const chosen = SHOWCASE.find((s) => s.code === form.destination);
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
            <div className="eyebrow">AI travel agent · {destinations.length || 100} destinations</div>
            <h1>See it before <span>you book it.</span></h1>
            <p className="lede">
              Pick any of {destinations.length || 100} cities across Europe, the Americas and Asia. Your AI agent
              finds real hotels, sights and weather, ranks the options, and shows you the best choice at a glance.
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
            {config.openai && (
              <div className="ai-box">
                <label className="field">
                  <span>✨ Build a whole trip from a prompt</span>
                  <textarea
                    rows={3}
                    value={freeText}
                    maxLength={1500}
                    placeholder="e.g. Four days in Porto in December for two, about £1,500. We love wine, old pubs, museums and a good market."
                    onChange={(e) => setFreeText(e.target.value)}
                  />
                </label>
                <div className="ai-actions">
                  <input ref={fileRef} type="file" accept="image/*" hidden onChange={pickImage} />
                  {image ? (
                    <span className="thumb-chip">
                      <img src={image} alt="Your inspiration" />
                      <button type="button" onClick={() => setImage(null)} aria-label="Remove photo">×</button>
                    </span>
                  ) : (
                    <button type="button" className="btn ghost sm" onClick={() => fileRef.current?.click()}>📷 Add a photo of the vibe you like</button>
                  )}
                  <button type="button" className="btn primary sm" disabled={parsing || loading || (freeText.trim().length < 3 && !image)} onClick={build}>
                    {parsing ? "Reading…" : "Build my whole trip"}
                  </button>
                </div>
                {image && <p className="fine tight">The photo is shrunk on your device and sent to OpenAI only for this request. It is not stored, and the model is told not to identify anyone in it.</p>}
                {assumptions.length > 0 && (
                  <ul className="assume">
                    {assumptions.map((a) => <li key={a}>{a}</li>)}
                  </ul>
                )}
                {profile && (
                  <div className="profile-mini">
                    <b>Your travel profile</b>
                    <p className="muted">{profile.summary}</p>
                    <div className="chips">
                      {profile.keywords.map((k) => <span key={k} className="tag hit">{k}</span>)}
                      {profile.place_types.map((k) => <span key={k} className="tag">{PLACE_TYPE_LABEL[k] || k}</span>)}
                    </div>
                    <button type="button" className="link-btn plain" onClick={forgetProfile}>Forget my profile</button>
                  </div>
                )}
              </div>
            )}

            <div className="dest-grid" role="radiogroup" aria-label="Popular destinations">
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
                <DestSelect value={form.origin} onChange={(v) => set({ origin: v })} destinations={destinations} exclude={form.destination} />
              </label>
              <label className="field">
                <span>To</span>
                <DestSelect value={form.destination} onChange={(v) => set({ destination: v })} destinations={destinations} exclude={form.origin} />
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
            <p className="fine tight">The first search for a city can take up to a minute while live data is gathered. After that it is fast.</p>
          </motion.form>
        </div>
      </section>

      <section className="wrap section">
        <div className="section-head">
          <h2>Popular right now</h2>
          <p>Naples, Lisbon, Tokyo and Dubai also come with hand-picked highlights and costs. Every other city uses live sources.</p>
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
