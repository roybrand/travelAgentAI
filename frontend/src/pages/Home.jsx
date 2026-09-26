import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Link, useNavigate } from "react-router-dom";
import { buildTrip } from "../api";
import { tripDefaults, useTrip } from "../state/TripContext.jsx";
import { INTERESTS, SHOWCASE } from "../lib/constants";
import { isoDate } from "../lib/format";
import { PLACE_TYPE_LABEL, resizeImage } from "../lib/profile";
import DestSelect from "../components/DestSelect.jsx";
import Photo from "../components/Photo.jsx";
import PlanningOverlay from "../components/PlanningOverlay.jsx";

const FEATURES = [
  ["109 destinations, live data", "Europe, the Americas, Asia and Australia. Real weather, real sights and photos, real hotels and restaurants from free public sources."],
  ["Ranked, not just listed", "Every flight and stay is scored on price, quality, your interests and budget fit, then combined into one best pick."],
  ["Honest about what it knows", "Every price and data source is labelled: live, estimate or demo. Nothing is invented and passed off as real."],
  ["The right time to go", "Your dates are scored against real historical weather for the destination, with a nudge when a better window exists."],
];

// A few real, varied examples so the box never faces someone with a blank page. Clicking one fills it in --
// nothing is sent until they choose to.
const EXAMPLES = [
  "5 days in Tokyo this spring, we love food, temples and a good night out",
  "Long weekend in Barcelona for 4 friends — nightlife, beach and tapas",
  "10 days across Paris, Rome and Athens for two, food, ruins and a little beach time",
  "A week in Sydney in December, beaches, hikes and good coffee",
];

export default function Home() {
  const { form, setForm, plan, loading, error, setError, config, destinations, profile, setProfile, forgetProfile, trip, setReadback } = useTrip();
  const navigate = useNavigate();
  const [slide, setSlide] = useState(0);
  // Two separate processes with their own state and their own button. The form never reads the prompt,
  // and the prompt never reads or changes the form. `active` says which one started the current search.
  const [formError, setFormError] = useState("");
  const [promptError, setPromptError] = useState("");
  const [active, setActive] = useState("form");
  const [freeText, setFreeText] = useState("");
  const [parsing, setParsing] = useState(false);
  const [image, setImage] = useState(null);
  const fileRef = useRef(null);
  // The manual form is tucked away by default so the AI box reads as the product, not "option 1 of 2".
  const [showForm, setShowForm] = useState(false);
  const [assumptions, setAssumptions] = useState([]);
  // Set when the words did not name a usable city: we ask instead of guessing.
  const [ask, setAsk] = useState(null);
  const [originPick, setOriginPick] = useState("");

  useEffect(() => {
    const t = setInterval(() => setSlide((s) => (s + 1) % SHOWCASE.length), 6500);
    return () => clearInterval(t);
  }, []);

  const set = (patch) => setForm((f) => ({ ...f, ...patch }));
  const route = form.destinations?.length ? form.destinations : [form.destination].filter(Boolean);
  const setRoute = (next) => {
    const clean = next.filter(Boolean);
    set({ destinations: clean, destination: clean[0] || "" });
  };
  const setStop = (index, code) => setRoute(route.map((x, i) => (i === index ? code : x)));
  const addStop = () => {
    const next = destinations.find((d) => d.code !== form.origin && !route.includes(d.code));
    if (next) setRoute([...route, next.code]);
  };
  const removeStop = (index) => setRoute(route.filter((_, i) => i !== index));
  const toggleInterest = (k) =>
    set({ interests: form.interests.includes(k) ? form.interests.filter((x) => x !== k) : [...form.interests, k] });

  function validate(p) {
    if (!p.origin) return "Choose where you are flying from.";
    const stops = p.destinations?.length ? p.destinations : [p.destination].filter(Boolean);
    if (!stops.length) return "Choose at least one stop.";
    if (stops.includes(p.origin)) return "Your route stops must differ from where you are flying from.";
    if (new Set(stops).size !== stops.length) return "Each stop in the route should be different.";
    if (!p.start_date || !p.end_date || p.end_date <= p.start_date) return "The return date must be after departure.";
    if (p.budget !== null && !(p.budget > 0)) return "Budget must be greater than zero.";
    return "";
  }

  /** Put the form back to its defaults. Does not touch the prompt or any trip. */
  function resetForm() {
    setForm(tripDefaults());
    setFormError("");
    setError("");
  }

  /** Empty the prompt box. Does not touch the form or any trip. */
  function clearPrompt() {
    setFreeText("");
    setImage(null);
    setAssumptions([]);
    setAsk(null);
    setOriginPick("");
    setPromptError("");
    setError("");
  }

  async function submit(e) {
    e.preventDefault();
    const payload = { ...form, budget: form.budget === "" || form.budget == null ? null : Number(form.budget) };
    const msg = validate(payload);
    setFormError(msg);
    if (msg) return;
    setError("");
    setActive("form");
    setReadback(null);
    if (await plan({ ...payload, place_types: [] })) navigate("/trip");
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

  /** Plan from the words alone. Anything they did not say gets a fixed default (never a value from the form). */
  async function planFromPrompt(built, prof) {
    const base = tripDefaults();
    const { _originPicked, ...builtFields } = built;
    const payload = {
      ...base,
      ...builtFields,
      destinations: builtFields.destinations?.length ? builtFields.destinations : (builtFields.destination ? [builtFields.destination] : []),
      destination: builtFields.destinations?.[0] || builtFields.destination,
      interests: prof?.interests?.length ? prof.interests : builtFields.interests || [],
      budget: builtFields.budget ?? null,
      place_types: prof?.place_types ?? [],
    };
    if (!payload.origin) {
      setOriginPick("");
      setAsk({ kind: "origin", prof, built });
      return;
    }
    const msg = validate(payload);
    if (msg) throw new Error(`${msg} Try describing the trip again.`);
    const saidKeys = Object.keys(builtFields).filter((k) => !(_originPicked && k === "origin"));
    const rb = {
      said: [...new Set([...saidKeys, ...(prof?.interests?.length ? ["interests"] : [])])],
      selected: _originPicked ? ["origin"] : [],
      prompt: freeText.trim().slice(0, 240),
      photo: !!image,
    };
    setReadback(rb);
    setActive("prompt");
    if (await plan(payload, { readback: rb })) navigate("/trip");
  }

  /** Prompt (and optional photo) -> trip fields + a traveler profile -> plan the whole trip. */
  async function build() {
    setParsing(true);
    setPromptError("");
    setError("");
    setAssumptions([]);
    setAsk(null);
    setActive("prompt");
    try {
      const { assumptions: notes = [], profile: prof, destination_choices: choices = [], place_mentioned: mentioned, unsupported_places: unsupported = [], ...built } = await buildTrip(freeText, image);
      const gotSomething = Object.keys(built).length || choices.length || unsupported.length || prof?.place_types?.length || prof?.interests?.length;
      if (!gotSomething) throw new Error("I could not find any trip details in that. Try adding a place, or a photo of somewhere you like.");
      setAssumptions(notes);
      setOriginPick("");
      if (prof) setProfile(prof);
      if (!built.destination && !built.destinations?.length) {
        setAsk({ kind: "destination", choices, mentioned, unsupported, prof, built });
        return;
      }
      setParsing(false);
      await planFromPrompt(built, prof);
    } catch (e) {
      setPromptError(e.message);
    } finally {
      setParsing(false);
    }
  }

  async function pickCity(code) {
    const { prof, built } = ask;
    setAsk(null);
    setPromptError("");
    try {
      await planFromPrompt({ ...built, destination: code, destinations: [code] }, prof);
    } catch (e) {
      setPromptError(e.message);
    }
  }

  async function pickOrigin() {
    const { prof, built } = ask;
    if (!originPick) {
      setPromptError("Choose where you are flying from.");
      return;
    }
    setAsk(null);
    setPromptError("");
    try {
      await planFromPrompt({ ...built, origin: originPick, _originPicked: true }, prof);
    } catch (e) {
      setPromptError(e.message);
    }
  }

  const chosen = SHOWCASE.find((s) => s.code === (route[0] || form.destination));
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
            <div className="eyebrow">AI travel agent · {destinations.length || 109} destinations</div>
            <h1>See it before <span>you book it.</span></h1>
            <p className="lede">
              Pick any of {destinations.length || 109} cities across Europe, the Americas, Asia and Australia. Your AI agent
              finds real hotels, sights and weather, ranks the options, and shows you the best choice at a glance.
            </p>
          </motion.div>

          <div className="process-stack">
            {config.openai && (
              <motion.section
                className="search glass prompt-card ai-card"
                aria-label="Describe your trip"
                initial={{ opacity: 0, y: 24 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.25, duration: 0.6 }}
              >
  <div className="ai-box">
                  <div className="ai-heading">
                    <span className="ai-orb" aria-hidden="true" />
                    <div>
                      <h2 className="process-title">Tell me about your dream trip</h2>
                      <p className="muted">Talk to me the way you'd tell a friend. I'll work out the route, dates and vibe, then search real flights, hotels and things to do myself.</p>
                    </div>
                  </div>
                  <label className="field">
                    <span className="sr-only">Describe your trip</span>
                    <textarea
                      rows={3}
                      value={freeText}
                      maxLength={1500}
                      placeholder="e.g. Ten days across Paris, Rome and Athens for two. We love food, ruins, museums and a beach day."
                      onChange={(e) => setFreeText(e.target.value)}
                    />
                  </label>
                  {!freeText && !image && (
                    <div className="example-chips">
                      <span className="example-label">Try one:</span>
                      {EXAMPLES.map((ex) => (
                        <button type="button" key={ex} className="chip example" onClick={() => setFreeText(ex)}>{ex}</button>
                      ))}
                    </div>
                  )}
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
                    <button type="button" className="btn ghost sm" onClick={clearPrompt} disabled={parsing || loading}>Clear</button>
                  </div>
                  {image && <p className="fine tight">The photo is shrunk on your device and sent to OpenAI only for this request. It is not stored, and the model is told not to identify anyone in it.</p>}
                  {(promptError || (active === "prompt" && error)) && <p className="err" role="alert">{promptError || error}</p>}
                  {ask && (
                    <div className="ask" role="alert">
                      {ask.kind === "origin" ? (
                        <>
                          <b>Where are you flying from?</b>
                          <p className="muted">I will not assume London or any other city. Pick your departure city and I will plan the same trip.</p>
                          <div className="ask-origin">
                            <DestSelect value={originPick} onChange={setOriginPick} destinations={destinations} exclude={ask.built?.destinations || ask.built?.destination} placeholder="Flying from" />
                            <button type="button" className="btn primary sm" onClick={pickOrigin}>Continue</button>
                          </div>
                        </>
                      ) : (
                        <>
                          <b>
                            {ask.unsupported?.length
                          ? `${ask.unsupported.join(", ")} ${ask.unsupported.length > 1 ? "are" : "is"} not in this planner yet.`
                          : ask.choices.length
                          ? `Which city did you mean${ask.mentioned ? ` in ${ask.mentioned}` : ""}?`
                          : ask.mentioned
                            ? `“${ask.mentioned}” is not one of our ${destinations.length || 109} cities yet.`
                              : "I could not tell where you want to go."}
                          </b>
                          <p className="muted">
                            {ask.unsupported?.length && ask.choices.length
                          ? "I can plan the supported part below, or you can change the request."
                          : ask.choices.length ? "Pick one and I will plan it with everything else you said." : "Name one of the cities in your description and try again."}
                          </p>
                          {ask.choices.length > 0 && (
                            <div className="chips">
                              {ask.choices.map((c) => <button type="button" key={c.code} className="chip" onClick={() => pickCity(c.code)}>{c.city}</button>)}
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  )}
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
              </motion.section>
            )}

            {trip && <p className="fine tight last-trip-note">Your last trip is still saved. <Link to="/trip">Go back to it</Link> or plan a different one.</p>}

            {config.openai && !showForm && (
              <button type="button" className="form-toggle" onClick={() => setShowForm(true)}>
                Prefer to fill in the details yourself? <span>Open the form →</span>
              </button>
            )}

            <AnimatePresence>
            {(showForm || !config.openai) && (
            <motion.form
              className="search glass"
              onSubmit={submit}
              noValidate
              aria-label="Plan with the form"
              initial={config.openai ? { opacity: 0, height: 0 } : { opacity: 0, y: 24 }}
              animate={config.openai ? { opacity: 1, height: "auto" } : { opacity: 1, y: 0 }}
              exit={config.openai ? { opacity: 0, height: 0 } : undefined}
              transition={{ duration: config.openai ? 0.35 : 0.6, delay: config.openai ? 0 : 0.35 }}
            >
              <div className="card-head">
                <h2 className="process-title">Plan with the form</h2>
                {config.openai && <button type="button" className="link-btn plain" onClick={() => setShowForm(false)}>Hide the form</button>}
              </div>
              <div className="dest-grid" role="radiogroup" aria-label="Popular destinations">
                {SHOWCASE.map((s) => (
                  <button
                    type="button"
                    key={s.code}
                    role="radio"
                    aria-checked={chosen?.code === s.code}
                    className={`dest ${chosen?.code === s.code ? "on" : ""}`}
                    onClick={() => setRoute([s.code])}
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
                  <DestSelect value={form.origin} onChange={(v) => set({ origin: v })} destinations={destinations} exclude={form.destination} placeholder="Flying from" />
                </label>
                <label className="field">
                  <span>Route stops</span>
                  <div className="route-stops">
                    {route.map((code, index) => (
                      <div className="route-stop" key={`${code}-${index}`}>
                        <b>{index + 1}</b>
                        <DestSelect value={code} onChange={(v) => setStop(index, v)} destinations={destinations} exclude={[form.origin, ...route.filter((_, i) => i !== index)]} />
                        {route.length > 1 && <button type="button" className="linkbtn danger" onClick={() => removeStop(index)}>Remove</button>}
                      </div>
                    ))}
                    <button type="button" className="btn ghost sm" onClick={addStop} disabled={!destinations.length || route.length >= 8}>+ Add another city or country stop</button>
                  </div>
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

              {(formError || (active === "form" && error)) && <p className="err" role="alert">{formError || error}</p>}
              <div className="submit-row">
                <button className="btn primary big" type="submit" disabled={loading}>
                  {loading ? "Planning…" : "Plan my trip"}
                </button>
                <button className="btn ghost big" type="button" onClick={resetForm} disabled={loading}>↺ Reset</button>
              </div>
              <p className="fine tight">The first search for a city can take up to a minute while live data is gathered. After that it is fast.</p>
            </motion.form>
            )}
            </AnimatePresence>
          </div>
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
                setRoute([s.code]);
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
