import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { fetchDealOptions, partner as api } from "../api";
import { useTrip } from "../state/TripContext.jsx";
import { TAG_LABEL } from "../lib/constants";
import { isoDate, longDate } from "../lib/format";
import { PLACE_TYPE_LABEL } from "../lib/profile";
import DealCard from "../components/DealCard.jsx";
import DestSelect from "../components/DestSelect.jsx";
import BackLink from "../components/BackLink.jsx";

const TOKEN_KEY = "wf.partner.v1";
const loadToken = () => {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
};
const saveToken = (t) => {
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage may be unavailable */
  }
};

const plusDays = (n) => {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return isoDate(d);
};
const tagLabel = (k) => TAG_LABEL[k] || PLACE_TYPE_LABEL[k] || k;

function Field({ label, hint, children, wide }) {
  return (
    <label className={`field ${wide ? "wide" : ""}`}>
      {label}
      {children}
      {hint && <small className="hint">{hint}</small>}
    </label>
  );
}

// ---------------------------------------------------------------- sign up / sign in

function Landing({ onAuth, options }) {
  const { destinations, form } = useTrip();
  const [mode, setMode] = useState("register");
  const [f, setF] = useState({ name: "", email: "", password: "", business_type: "restaurant", city: form.destination });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = mode === "register" ? await api.register(f) : await api.login({ email: f.email, password: f.password });
      onAuth(res.token);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="wrap page">
      <BackLink fallback="/" />
      <div className="partner-hero">
        <div>
          <div className="eyebrow">For businesses</div>
          <h1 className="h2">Reach travelers who are already planning your city</h1>
          <p className="muted lede">
            List a deal for free. Travelers see it on their trip plan, on the deals page and, if they opt in, on their phone when they walk past. You pay nothing to list.
          </p>
          <ol className="steps">
            <li><b>Create an account.</b> Hotels, restaurants, bars, tours, clubs, car rental and airlines are all welcome.</li>
            <li><b>Post a deal.</b> A price, an honest usual price, the dates, the terms and your booking link.</li>
            <li><b>We review it.</b> Usually the same day. Approved deals go live and are ranked by how well they fit each traveler.</li>
            <li><b>See the results.</b> Views and clicks for every deal, and a feed API if you have many.</li>
          </ol>
          <p className="fine">Deals are labelled “Partner deal” everywhere. We never rank a deal higher because of who you are or what you pay.</p>
        </div>
        <form className="card pad auth" onSubmit={submit}>
          <div className="tabs-inline">
            <button type="button" className={mode === "register" ? "on" : ""} onClick={() => setMode("register")}>Create account</button>
            <button type="button" className={mode === "login" ? "on" : ""} onClick={() => setMode("login")}>Sign in</button>
          </div>
          {mode === "register" && (
            <>
              <Field label="Business name"><input required minLength={2} maxLength={80} value={f.name} onChange={set("name")} autoComplete="organization" /></Field>
              <div className="fields">
                <Field label="Type of business">
                  <select value={f.business_type} onChange={set("business_type")}>
                    {(options?.categories || []).map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
                  </select>
                </Field>
                <Field label="City"><DestSelect value={f.city} onChange={(c) => setF((x) => ({ ...x, city: c }))} destinations={destinations} /></Field>
              </div>
            </>
          )}
          <Field label="Email"><input type="email" required value={f.email} onChange={set("email")} autoComplete="email" /></Field>
          <Field label="Password" hint={mode === "register" ? "At least 10 characters." : undefined}>
            <input type="password" required minLength={mode === "register" ? 10 : 1} value={f.password} onChange={set("password")} autoComplete={mode === "register" ? "new-password" : "current-password"} />
          </Field>
          {error && <p className="error" role="alert">{error}</p>}
          <button className="btn primary full" disabled={busy}>{busy ? "Please wait…" : mode === "register" ? "Create account" : "Sign in"}</button>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- deal form

function blank(p) {
  return {
    title: "", description: "", category: p.business_type, dest: p.city, address: "", lat: "", lng: "",
    price: "", reference_price: "", currency: "GBP", price_note: "", valid_from: plusDays(0), valid_to: plusDays(30),
    stock: "", url: "", terms: "", photo_url: "", tags: [],
  };
}

function fromDeal(d) {
  const s = (v) => (v == null ? "" : String(v));
  return {
    title: d.title, description: d.description, category: d.category, dest: d.dest, address: s(d.address), lat: s(d.lat), lng: s(d.lng),
    price: s(d.price), reference_price: s(d.reference_price), currency: d.currency, price_note: s(d.price_note),
    valid_from: d.valid_from, valid_to: d.valid_to, stock: s(d.stock), url: d.url, terms: d.terms, photo_url: s(d.photo_url), tags: d.tags,
  };
}

const num = (v) => (v === "" || v == null ? null : Number(v));
const text = (v) => (v && String(v).trim() ? String(v).trim() : null);

function payload(f) {
  return {
    title: f.title, description: f.description, category: f.category, dest: f.dest, address: text(f.address),
    lat: num(f.lat), lng: num(f.lng), price: num(f.price) ?? 0, reference_price: num(f.reference_price), currency: f.currency,
    price_note: text(f.price_note), valid_from: f.valid_from, valid_to: f.valid_to, stock: num(f.stock), url: f.url.trim(),
    terms: f.terms, photo_url: text(f.photo_url), tags: f.tags,
  };
}

function previewOf(f, me, options) {
  const price = num(f.price) ?? 0;
  const ref = num(f.reference_price);
  const cat = options?.categories.find((c) => c.key === f.category);
  return {
    id: null, title: f.title || "Your deal title", description: f.description || "Describe the offer in a sentence or two.",
    category: f.category, category_label: cat?.label || f.category, city: "", price, reference_price: ref, currency: f.currency,
    price_note: f.price_note, discount_pct: ref && ref > price ? Math.round((1 - price / ref) * 100) : 0,
    valid_to: f.valid_to, address: f.address, stock: num(f.stock), photo_url: f.photo_url || null, partner_name: me.partner.name,
    terms: f.terms || "Your terms will appear here.", match: [], why: [], url: f.url,
  };
}

function DealForm({ token, me, options, editing, onSaved, onCancel }) {
  const { destinations } = useTrip();
  const [f, setF] = useState(() => (editing ? fromDeal(editing) : blank(me.partner)));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [geo, setGeo] = useState("");
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const needsLocation = options?.categories.find((c) => c.key === f.category)?.needs_location !== false;

  useEffect(() => setF(editing ? fromDeal(editing) : blank(me.partner)), [editing, me.partner]);

  const geocodeAddress = async () => {
    const r = await api.geocode(token, f.address, f.dest);
    setF((x) => ({ ...x, lat: String(r.lat), lng: String(r.lng) }));
    setGeo(`Found: ${r.label}`);
    return r;
  };

  const findAddress = async () => {
    setGeo("Searching…");
    try {
      await geocodeAddress();
    } catch (e) {
      setGeo(e.message);
    }
  };

  const toggleTag = (t) => setF((x) => ({ ...x, tags: x.tags.includes(t) ? x.tags.filter((y) => y !== t) : x.tags.length < 6 ? [...x.tags, t] : x.tags }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      let form = f;
      // Coordinates are found from the address automatically. A partner only needs to
      // type coordinates themselves if the address search can't find the place.
      if (needsLocation && (!f.lat || !f.lng)) {
        if (f.address.trim().length < 4) throw new Error("Enter a street address, or the exact coordinates.");
        setGeo("Searching…");
        const r = await geocodeAddress();
        form = { ...f, lat: String(r.lat), lng: String(r.lng) };
      }
      if (editing) await api.update(token, editing.id, payload(form));
      else await api.create(token, payload(form));
      onSaved(editing ? "Saved. Changes go back to review before they show." : "Sent for review. It goes live once approved.");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const preview = useMemo(() => previewOf(f, me, options), [f, me, options]);

  return (
    <div className="deal-form-wrap">
      <form className="card pad" onSubmit={submit}>
        <h2 className="card-title">{editing ? "Edit deal" : "New deal"}</h2>
        <div className="fields">
          <Field label="Title" wide><input required minLength={5} maxLength={90} value={f.title} onChange={set("title")} placeholder="Two-course dinner with wine" /></Field>
          <Field label="What is included" wide><textarea required minLength={10} maxLength={600} rows={3} value={f.description} onChange={set("description")} /></Field>
          <Field label="Category">
            <select value={f.category} onChange={set("category")}>{options?.categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}</select>
          </Field>
          <Field label="Destination"><DestSelect value={f.dest} onChange={(c) => setF((x) => ({ ...x, dest: c }))} destinations={destinations} /></Field>
          {needsLocation && (
            <>
              <Field label="Street address" wide hint="We find the map coordinates from this automatically when you save.">
                <span className="inline">
                  <input value={f.address} onChange={set("address")} maxLength={160} placeholder="Rua das Flores 10" />
                  <button type="button" className="btn ghost sm" onClick={findAddress} disabled={f.address.trim().length < 4}>Find on map</button>
                </span>
                {geo && <small className="hint">{geo}</small>}
              </Field>
              <Field label="Latitude (optional)" hint="Only needed if the address search can't find the place.">
                <input type="number" step="any" min={-90} max={90} value={f.lat} onChange={set("lat")} />
              </Field>
              <Field label="Longitude (optional)" hint="Only needed if the address search can't find the place.">
                <input type="number" step="any" min={-180} max={180} value={f.lng} onChange={set("lng")} />
              </Field>
            </>
          )}
          <Field label="Deal price"><input required type="number" min={0} step="0.01" value={f.price} onChange={set("price")} /></Field>
          <Field label="Currency"><select value={f.currency} onChange={set("currency")}>{(options?.currencies || ["GBP"]).map((c) => <option key={c}>{c}</option>)}</select></Field>
          <Field label="Usual price (optional)" hint="Only fill this in if it is the genuine normal price. It is shown as the discount.">
            <input type="number" min={0} step="0.01" value={f.reference_price} onChange={set("reference_price")} />
          </Field>
          <Field label="Price note (optional)"><input maxLength={40} value={f.price_note} onChange={set("price_note")} placeholder="per person, per night…" /></Field>
          <Field label="Valid from"><input required type="date" value={f.valid_from} onChange={set("valid_from")} /></Field>
          <Field label="Valid until"><input required type="date" value={f.valid_to} min={f.valid_from} onChange={set("valid_to")} /></Field>
          <Field label="Places or seats left (optional)"><input type="number" min={1} value={f.stock} onChange={set("stock")} /></Field>
          <Field label="Booking link" hint="Must start with https://"><input required type="url" value={f.url} onChange={set("url")} placeholder="https://" /></Field>
          <Field label="Photo link (optional)" hint="A photo you own or have the right to use. https:// only." wide><input type="url" value={f.photo_url} onChange={set("photo_url")} placeholder="https://" /></Field>
          <Field label="Terms" wide hint="Days, times, exclusions, how to redeem."><textarea required minLength={10} maxLength={800} rows={3} value={f.terms} onChange={set("terms")} /></Field>
        </div>
        <div className="tag-pick">
          <span className="muted">Who is it for? (optional, up to 6)</span>
          <div className="chips">
            {options?.tags.map((t) => <button key={t} type="button" className="chip" aria-pressed={f.tags.includes(t)} onClick={() => toggleTag(t)}>{tagLabel(t)}</button>)}
          </div>
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="form-actions">
          <button className="btn primary" disabled={busy}>{busy ? "Saving…" : editing ? "Save changes" : "Submit for review"}</button>
          {editing && <button type="button" className="btn ghost" onClick={onCancel}>Cancel</button>}
        </div>
        <p className="fine">Every deal is checked by a person before it appears. Editing an approved deal sends it back for review.</p>
      </form>
      <div className="preview">
        <div className="eyebrow">Live preview</div>
        <DealCard deal={preview} preview />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- dashboard

const STATUS = { pending: ["In review", "warn"], approved: ["Live", "ok"], rejected: ["Not approved", "bad"], ended: ["Ended", "muted"] };

function statusOf(d) {
  if (d.status === "approved" && d.paused) return ["Paused", "muted"];
  if (d.status === "approved" && new Date(d.valid_to + "T23:59:59") < new Date()) return ["Expired", "muted"];
  return STATUS[d.status] || [d.status, "muted"];
}

function ApiKeyPanel({ token, has }) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const make = async () => {
    if (has && !window.confirm("This replaces your current key. Anything using the old key stops working. Continue?")) return;
    setBusy(true);
    try {
      setKey((await api.apiKey(token)).api_key);
    } finally {
      setBusy(false);
    }
  };
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return (
    <section className="card pad">
      <h2 className="card-title">Feed API</h2>
      <p className="muted">Have many deals or a booking system? Send them in bulk. Each item needs a stable <code>external_id</code> and a <code>valid_from</code>, and goes through the same review.</p>
      <button className="btn ghost sm" onClick={make} disabled={busy}>{has ? "Replace my API key" : "Create an API key"}</button>
      {key && (
        <div className="keybox">
          <p className="fine">Copy it now. It is shown only once.</p>
          <code>{key}</code>
          <pre>{`curl -X POST ${origin}/api/partner-feed \\
  -H "X-API-Key: ${key}" -H "Content-Type: application/json" \\
  -d '{"deals":[{"external_id":"menu-1","title":"…","description":"…","category":"restaurant","dest":"OPO","lat":41.14,"lng":-8.61,"price":24,"currency":"EUR","valid_from":"2026-10-01","valid_to":"2026-10-31","url":"https://…","terms":"…"}]}'`}</pre>
        </div>
      )}
    </section>
  );
}

function Dashboard({ token, onSignOut }) {
  const [me, setMe] = useState(null);
  const [options, setOptions] = useState(null);
  const [editing, setEditing] = useState(null);
  const [adding, setAdding] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api.me(token).then(setMe).catch((e) => (e.status === 401 ? onSignOut() : setError(e.message)));
  }, [token, onSignOut]);
  useEffect(load, [load]);
  useEffect(() => void fetchDealOptions().then(setOptions).catch(() => {}), []);

  if (!me) return <div className="wrap page"><p className="muted">{error || "Loading…"}</p></div>;
  const { totals } = me;
  const ctr = totals.impressions ? `${((totals.clicks / totals.impressions) * 100).toFixed(1)}%` : "–";
  const act = async (fn) => {
    setError("");
    try {
      await fn();
      load();
    } catch (e) {
      setError(e.message);
    }
  };
  const saved = (msg) => {
    setNote(msg);
    setEditing(null);
    setAdding(false);
    load();
  };

  return (
    <div className="wrap page">
      <BackLink fallback="/" />
      <div className="page-head">
        <div>
          <div className="eyebrow">Partner portal</div>
          <h1 className="h2">{me.partner.name}</h1>
          <p className="muted">{me.partner.email}</p>
        </div>
        <div className="head-actions">
          <button className="btn primary" onClick={() => { setAdding(true); setEditing(null); setNote(""); }}>+ New deal</button>
          <button className="btn ghost" onClick={onSignOut}>Sign out</button>
        </div>
      </div>

      <div className="stat-row">
        <div className="card stat"><b>{totals.live}</b><span>Live deals</span></div>
        <div className="card stat"><b>{totals.pending}</b><span>In review</span></div>
        <div className="card stat"><b>{totals.impressions}</b><span>Times shown</span></div>
        <div className="card stat"><b>{totals.clicks}</b><span>Clicks to your link</span></div>
        <div className="card stat"><b>{ctr}</b><span>Click rate</span></div>
      </div>

      {note && <p className="notice" role="status">{note}</p>}
      {error && <p className="error" role="alert">{error}</p>}

      {(adding || editing) && (
        <DealForm token={token} me={me} options={options} editing={editing} onSaved={saved} onCancel={() => { setEditing(null); setAdding(false); }} />
      )}

      <section className="card pad">
        <h2 className="card-title">Your deals</h2>
        {me.deals.length === 0 && <p className="muted">No deals yet. Add your first one. It takes about two minutes.</p>}
        {me.deals.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Deal</th><th>Status</th><th>Valid until</th><th>Shown</th><th>Clicks</th><th /></tr></thead>
              <tbody>
                {me.deals.map((d) => {
                  const [text, tone] = statusOf(d);
                  return (
                    <tr key={d.id}>
                      <td>
                        <b>{d.title}</b>
                        <small>{d.category_label} · {d.city}</small>
                        {d.status === "rejected" && d.reject_reason && <small className="reject">Reviewer: {d.reject_reason}</small>}
                      </td>
                      <td><span className={`src-badge ${tone}`}>{text}</span></td>
                      <td>{longDate(d.valid_to)}</td>
                      <td>{d.impressions}</td>
                      <td>{d.clicks}</td>
                      <td className="row-actions">
                        {d.status !== "ended" && <button className="linkbtn" onClick={() => { setEditing(d); setAdding(false); setNote(""); window.scrollTo({ top: 0, behavior: "smooth" }); }}>Edit</button>}
                        {d.status === "approved" && <button className="linkbtn" onClick={() => act(() => api.pause(token, d.id, !d.paused))}>{d.paused ? "Resume" : "Pause"}</button>}
                        {d.status !== "ended" && <button className="linkbtn danger" onClick={() => window.confirm("End this deal? This cannot be undone.") && act(() => api.end(token, d.id))}>End</button>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <ApiKeyPanel token={token} has={me.partner.has_api_key} />
      <p className="fine">Questions about a review decision? Reply to the email you signed up with. See <Link to="/deals">how deals look to travelers</Link>.</p>
    </div>
  );
}

export default function Partners() {
  const [token, setToken] = useState(loadToken);
  const [options, setOptions] = useState(null);
  useEffect(() => void fetchDealOptions().then(setOptions).catch(() => {}), []);
  const signIn = (t) => {
    saveToken(t);
    setToken(t);
  };
  const signOut = useCallback(() => {
    const t = loadToken();
    if (t) api.logout(t);
    saveToken("");
    setToken("");
  }, []);
  return token ? <Dashboard token={token} onSignOut={signOut} /> : <Landing onAuth={signIn} options={options} />;
}
