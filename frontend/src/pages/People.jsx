import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { people } from "../api";
import { usePeople } from "../state/PeopleContext.jsx";
import { useTrip } from "../state/TripContext.jsx";
import { longDate } from "../lib/format";
import { resizeImage } from "../lib/profile";
import DestSelect from "../components/DestSelect.jsx";
import PersonCard, { Avatar } from "../components/PersonCard.jsx";
import BackLink from "../components/BackLink.jsx";

const TABS = [["find", "Find people"], ["inbox", "Inbox"], ["profile", "My profile"]];

function Field({ label, hint, children }) {
  return (
    <label className="field">
      {label}
      {children}
      {hint && <small className="hint">{hint}</small>}
    </label>
  );
}

function Rules({ rules }) {
  return (
    <ul className="rules">{(rules || []).map((r) => <li key={r}>{r}</li>)}</ul>
  );
}

// ---------------------------------------------------------------- not signed in

function Landing() {
  const { signIn, options } = usePeople();
  const [mode, setMode] = useState("register");
  const [f, setF] = useState({ display_name: "", email: "", password: "", birth_year: "", agreed: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = mode === "register"
        ? await people.register({ ...f, birth_year: Number(f.birth_year) })
        : await people.login({ email: f.email, password: f.password });
      signIn(res.token);
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
          <div className="eyebrow">People</div>
          <h1 className="h2">Meet other travelers at the places you are going</h1>
          <p className="muted lede">
            Say which places you are going to, see who else is going, or tell the AI what you want to do and who you would like to do it with. When there is a match you can see each other's profile and, if you both agree, chat.
          </p>
          <ol className="steps">
            <li><b>Make a profile.</b> A name, a short bio, what you like, and (if you want) a photo of yourself.</li>
            <li><b>Register to places.</b> Tap “I'm going” on a club, bar or place. Others going can see your profile.</li>
            <li><b>Describe what you want.</b> “Live music tonight, someone relaxed who speaks Spanish.” We find people nearby who want the same.</li>
            <li><b>Say hi.</b> Chat opens only when they accept.</li>
          </ol>
          <div className="safety-note">
            <b>Your safety comes first</b>
            <Rules rules={options?.rules} />
            <p className="fine">You choose what to share. You can hide your profile, block or report anyone, and delete your account and data at any time. We never show your email, your exact age or your exact location.</p>
          </div>
        </div>
        <form className="card pad auth" onSubmit={submit}>
          <div className="tabs-inline">
            <button type="button" className={mode === "register" ? "on" : ""} onClick={() => setMode("register")}>Create account</button>
            <button type="button" className={mode === "login" ? "on" : ""} onClick={() => setMode("login")}>Sign in</button>
          </div>
          {mode === "register" && (
            <>
              <Field label="Display name" hint="Shown to other people. A first name is fine."><input required minLength={2} maxLength={40} value={f.display_name} onChange={set("display_name")} /></Field>
              <Field label="Year of birth" hint="Only used to check you are 18 or older. It is never shown."><input required type="number" min={1900} max={new Date().getFullYear() - 18} value={f.birth_year} onChange={set("birth_year")} /></Field>
            </>
          )}
          <Field label="Email"><input type="email" required value={f.email} onChange={set("email")} autoComplete="email" /></Field>
          <Field label="Password" hint={mode === "register" ? "At least 10 characters." : undefined}><input type="password" required value={f.password} onChange={set("password")} autoComplete={mode === "register" ? "new-password" : "current-password"} /></Field>
          {mode === "register" && (
            <label className="check">
              <input type="checkbox" checked={f.agreed} onChange={(e) => setF((x) => ({ ...x, agreed: e.target.checked }))} />
              <span>I am 18 or older and I accept the community rules.</span>
            </label>
          )}
          {error && <p className="error" role="alert">{error}</p>}
          <button className="btn primary full" disabled={busy || (mode === "register" && !f.agreed)}>{busy ? "Please wait…" : mode === "register" ? "Create account" : "Sign in"}</button>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- find people

function useLocation(fallbackCity, destinations) {
  const [pos, setPos] = useState(null);
  const [status, setStatus] = useState("");
  const ask = () => {
    if (!("geolocation" in navigator) || !window.isSecureContext) return setStatus("Location needs a secure connection (HTTPS) and a supported browser. Choose a city instead.");
    setStatus("Waiting for your location…");
    navigator.geolocation.getCurrentPosition(
      (p) => { setPos({ lat: p.coords.latitude, lng: p.coords.longitude, label: "your location" }); setStatus(""); },
      () => setStatus("Location was blocked. Choose a city instead."),
      { maximumAge: 60000, timeout: 20000 },
    );
  };
  const city = destinations.find((d) => d.code === fallbackCity);
  return { pos: pos || (city ? { lat: city.lat, lng: city.lng, label: `the centre of ${city.city}` } : null), ask, status, usingGps: !!pos, clear: () => setPos(null) };
}

function Find() {
  const { token, options, requests, refresh } = usePeople();
  const { destinations, form, trip } = useTrip();
  const [city, setCity] = useState(trip?.req.destination || form.destination);
  const loc = useLocation(city, destinations);
  const [text, setText] = useState("");
  const [radius, setRadius] = useState(3000);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  // null = read gender and age from the words; once the person picks any chip, their choice is used instead.
  const [want, setWant] = useState(null);
  const label = (k) => options?.activities.find((a) => a.key === k)?.label || k;
  const pick = (kind, v) => setWant((w) => {
    const cur = w || { genders: [], ages: [] };
    const list = cur[kind].includes(v) ? cur[kind].filter((x) => x !== v) : [...cur[kind], v];
    return { ...cur, [kind]: list };
  });

  const submit = async (e) => {
    e.preventDefault();
    if (!loc.pos) return setError("Choose a city or share your location first.");
    setBusy(true);
    setError("");
    try {
      const r = await people.looking(token, {
        text, lat: loc.pos.lat, lng: loc.pos.lng, radius_m: radius,
        ...(want ? { want_genders: want.genders, want_ages: want.ages } : {}),
      });
      setResult(r);
      refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const reopen = async (id) => {
    setBusy(true);
    try {
      setResult({ ...(await people.matches(token, id)), notes: [] });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const stop = async (id) => {
    await people.stopLooking(token, id).catch(() => {});
    if (result?.request?.id === id) setResult(null);
    refresh();
  };

  return (
    <>
      <form className="card pad find" onSubmit={submit}>
        <h2 className="card-title">Tell the AI what you want to do</h2>
        <Field label="What activity, and who would you like to do it with?" hint="For example: “Live music tonight, someone relaxed who speaks Spanish” or “Coffee and a walk tomorrow morning”. I match on the activity, language and vibe only.">
          <textarea rows={3} required minLength={4} maxLength={600} value={text} onChange={(e) => setText(e.target.value)} placeholder="Live music tonight in the old town, someone relaxed who speaks English or Spanish" />
        </Field>
        <div className="fields">
          <Field label="Where">
            <DestSelect value={city} onChange={(c) => { setCity(c); loc.clear(); }} destinations={destinations} />
          </Field>
          <Field label="How far">
            <select value={radius} onChange={(e) => setRadius(Number(e.target.value))}>
              {[[1000, "1 km"], [3000, "3 km"], [5000, "5 km"], [10000, "10 km"], [25000, "25 km"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </Field>
        </div>
        <div className="tag-pick">
          <span className="muted">Who would you like to meet? (optional)</span>
          <div className="chips">
            {options?.genders.map((g) => <button type="button" key={g} className="chip" aria-pressed={!!want?.genders.includes(g)} onClick={() => pick("genders", g)}>{g}</button>)}
            {options?.age_bands.map((a) => <button type="button" key={a} className="chip" aria-pressed={!!want?.ages.includes(a)} onClick={() => pick("ages", a)}>{a}</button>)}
            {want && <button type="button" className="linkbtn" onClick={() => setWant(null)}>Clear</button>}
          </div>
          <small className="hint">Leave these alone and I will read any gender or age you mention in your description. Only people who chose to share their gender are shown when you filter by it, and everyone can limit who is allowed to find them.</small>
        </div>
        <p className="fine">
          Searching around {loc.pos?.label || "…"}.{" "}
          <button type="button" className="linkbtn" onClick={loc.ask}>Use my location instead</button>
          {loc.status && <> {loc.status}</>}
        </p>
        <p className="fine">Only a rounded position (about 1 km) is stored with your request, and it ends when the day does. Other people see “within 1 km”, never where you are.</p>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="btn primary" disabled={busy || text.trim().length < 4}>{busy ? "Finding people…" : "Find people"}</button>
      </form>

      {requests.length > 0 && !result && (
        <section className="card pad">
          <h2 className="card-title">Your open requests</h2>
          <ul className="plain-list">
            {requests.map((r) => (
              <li key={r.id}>
                <span><b>{r.summary}</b><small>{r.tags.map(label).join(", ")} · {longDate(r.day)}</small></span>
                <span><button className="linkbtn" onClick={() => reopen(r.id)}>See matches</button><button className="linkbtn danger" onClick={() => stop(r.id)}>Stop</button></span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {result && (
        <section className="find-results">
          <div className="card pad understood">
            <b>Here is what I understood</b>
            <p className="muted">“{result.request.summary}”</p>
            <div className="facts-row">
              {result.request.tags.map((t) => <span key={t} className="tag hit">{label(t)}</span>)}
              <span className="tag">{longDate(result.request.day)}</span>
              {result.request.part !== "any" && <span className="tag">{result.request.part}</span>}
              {result.request.want_genders?.map((g) => <span key={g} className="tag hit">only {g}</span>)}
              {result.request.want_ages?.map((a) => <span key={a} className="tag hit">age {a}</span>)}
              {result.request.languages.map((l) => <span key={l} className="tag">{l}</span>)}
              {result.request.vibes.map((v) => <span key={v} className="tag">{v}</span>)}
            </div>
            {result.notes?.map((n) => <p className="fine" key={n}>{n}</p>)}
            <p className="fine">Your request stays open until the end of the day so people who ask later can find you. <button className="linkbtn danger" onClick={() => stop(result.request.id)}>Stop showing me</button></p>
          </div>

          <h2 className="card-title">People who want the same</h2>
          {result.people.length === 0 && (
            <div className="card pad empty">
              <b>No one matches yet.</b>
              <p className="muted">That is normal while Wayfinder People is new. Your request is open, so anyone who asks for something similar nearby will see you. Try widening the distance, or register to a place below so others can find you there.</p>
            </div>
          )}
          <div className="person-grid">{result.people.map((p) => <PersonCard key={p.id} person={p} />)}</div>

          {result.at_places.length > 0 && (
            <>
              <h2 className="card-title">People going to places near you</h2>
              {result.at_places.map((pl) => (
                <div key={pl.place_key} className="card pad">
                  <b>{pl.place_name}</b> <small className="muted">{pl.count} going · {pl.distance_m < 1000 ? `${pl.distance_m} m` : `${(pl.distance_m / 1000).toFixed(1)} km`} from the centre of your search</small>
                  <div className="person-grid">{pl.people.map((p) => <PersonCard key={p.id} person={p} compact />)}</div>
                </div>
              ))}
            </>
          )}
        </section>
      )}
    </>
  );
}

// ---------------------------------------------------------------- inbox and chat

function Chat({ chat, onClose, onChanged }) {
  const { token } = usePeople();
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const last = useRef(0);
  const box = useRef(null);

  const poll = useCallback(async () => {
    try {
      const r = await people.messages(token, chat.connection_id, last.current);
      if (r.messages.length) {
        last.current = r.messages[r.messages.length - 1].id;
        setMessages((m) => {
          const known = new Set(m.map((x) => x.id));
          return [...m, ...r.messages.filter((x) => !known.has(x.id))];
        });
      }
    } catch (e) {
      if (e.status === 404) onClose();
    }
  }, [token, chat.connection_id, onClose]);

  useEffect(() => {
    last.current = 0;
    setMessages([]);
    poll();
    const t = setInterval(poll, 4000);
    return () => clearInterval(t);
  }, [chat.connection_id, poll]);

  useEffect(() => {
    box.current?.scrollTo({ top: box.current.scrollHeight });
  }, [messages.length]);

  const send = async (e) => {
    e.preventDefault();
    if (!draft.trim()) return;
    try {
      const m = await people.send(token, chat.connection_id, draft);
      setDraft("");
      setError("");
      last.current = Math.max(last.current, m.id);
      setMessages((x) => [...x, m]);
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <section className="card chat">
      <header>
        <Avatar person={chat.person} size={40} />
        <b>{chat.person.display_name}</b>
        <button className="linkbtn" onClick={onClose}>Close</button>
      </header>
      {chat.person.demo && <p className="demo-banner">This is a demo profile. Its replies are automated, so it is not a real person.</p>}
      <div className="chat-log" ref={box}>
        {messages.length === 0 && <p className="fine">Say hello. Suggest a public place and time, and tell a friend where you are going.</p>}
        {messages.map((m) => <div key={m.id} className={`bubble ${m.mine ? "mine" : ""}`}>{m.body}</div>)}
      </div>
      {error && <p className="err">{error}</p>}
      <form className="chat-form" onSubmit={send}>
        <input value={draft} maxLength={500} onChange={(e) => setDraft(e.target.value)} placeholder="Write a message" />
        <button className="btn primary sm">Send</button>
      </form>
      <PersonCard person={chat.person} compact showActions={false} extra={<ChatSafety person={chat.person} onDone={() => { onChanged(); onClose(); }} />} />
    </section>
  );
}

function ChatSafety({ person, onDone }) {
  const { token, options } = usePeople();
  const [mode, setMode] = useState("");
  const [reason, setReason] = useState("harassment");
  const [note, setNote] = useState("");
  if (note) return <p className="fine">{note}</p>;
  return (
    <div className="safety">
      <button className="linkbtn" onClick={() => setMode(mode ? "" : "report")}>Report</button>
      <button className="linkbtn danger" onClick={async () => { if (window.confirm(`Block ${person.display_name}? The chat will close.`)) { await people.block(token, person.id); onDone(); } }}>Block</button>
      {mode && (
        <span className="report-box">
          <select value={reason} onChange={(e) => setReason(e.target.value)}>{(options?.report_reasons || []).map((r) => <option key={r}>{r}</option>)}</select>
          <button className="btn primary sm" onClick={async () => { await people.report(token, { user_id: person.id, reason, detail: "" }).catch(() => {}); setNote("Reported. A moderator will look at it."); }}>Send report</button>
        </span>
      )}
    </div>
  );
}

function Inbox({ openId }) {
  const { token } = usePeople();
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    people.connections(token).then(setData).catch((e) => setError(e.message));
  }, [token]);
  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    if (openId && data) {
      const chat = data.chats.find((c) => String(c.connection_id) === String(openId));
      if (chat) setOpen(chat);
    }
  }, [openId, data]);

  const answer = async (id, accept) => {
    await people.respond(token, id, accept).catch((e) => setError(e.message));
    load();
  };
  const closeChat = useCallback(() => setOpen(null), []);

  if (!data) return <p className="muted">{error || "Loading…"}</p>;
  return (
    <div className="inbox">
      {error && <p className="error">{error}</p>}
      {data.incoming.length > 0 && (
        <section className="card pad">
          <h2 className="card-title">Requests to connect</h2>
          {data.incoming.map((r) => (
            <div key={r.connection_id} className="request">
              <PersonCard person={r.person} showActions={false} extra={r.message && <p className="quote">“{r.message}”</p>} />
              <div className="form-actions">
                <button className="btn primary sm" onClick={() => answer(r.connection_id, true)}>Accept and chat</button>
                <button className="btn ghost sm" onClick={() => answer(r.connection_id, false)}>Decline</button>
              </div>
            </div>
          ))}
        </section>
      )}
      <section className="card pad">
        <h2 className="card-title">Chats</h2>
        {data.chats.length === 0 && <p className="muted">No chats yet. When someone accepts your request, or you accept theirs, the chat appears here.</p>}
        <ul className="plain-list chats">
          {data.chats.map((c) => (
            <li key={c.connection_id}>
              <button className="chat-row" onClick={() => setOpen(c)}>
                <Avatar person={c.person} size={40} />
                <span><b>{c.person.display_name}</b><small>{c.last ? `${c.last.mine ? "You: " : ""}${c.last.body}` : "Say hello"}</small></span>
              </button>
            </li>
          ))}
        </ul>
        {data.outgoing.length > 0 && <p className="fine">Waiting for an answer from: {data.outgoing.map((o) => o.person.display_name).join(", ")}.</p>}
      </section>
      {open && <Chat chat={open} onClose={closeChat} onChanged={load} />}
    </div>
  );
}

// ---------------------------------------------------------------- my profile

const PHOTO_TEXT = {
  none: "No photo yet. Others will see your initials.",
  pending: "Your photo is waiting for review. Only you can see it until it is approved.",
  approved: "Your photo is visible to people who can see your profile.",
  rejected: "That photo was not accepted. Please upload a clear photo of yourself.",
};

function Profile() {
  const { token, me, plans, blocked, options, refresh, signOut } = usePeople();
  const fileRef = useRef(null);
  const [f, setF] = useState(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (me) setF({ display_name: me.display_name, bio: me.bio, interests: me.interests, languages: me.languages, visible: me.visible,
      gender: me.gender || "", show_age: me.show_age, audience_genders: me.audience_genders, audience_ages: me.audience_ages });
  }, [me]);
  if (!me || !f) return null;

  const toggle = (k, v) => setF((x) => ({ ...x, [k]: x[k].includes(v) ? x[k].filter((y) => y !== v) : [...x[k], v] }));
  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await people.update(token, f);
      setNote("Saved.");
      refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  const upload = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    try {
      const r = await people.photo(token, await resizeImage(file, 512));
      setNote(r.status === "approved" ? "Photo added." : r.status === "pending" ? "Photo uploaded. It will show to others once it is reviewed." : "That photo was not accepted.");
      refresh();
    } catch (err) {
      setError(err.message);
    }
  };
  const remove = async () => {
    const password = window.prompt("This deletes your account, photo, plans, requests and messages for good. Type your password to confirm.");
    if (!password) return;
    try {
      await people.deleteMe(token, password);
      signOut();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="profile-grid">
      <form className="card pad" onSubmit={save}>
        <h2 className="card-title">My profile</h2>
        <div className="photo-row">
          <Avatar person={{ display_name: me.display_name, photo_url: me.photo_url }} size={96} />
          <div>
            <p className="muted">{PHOTO_TEXT[me.photo_status]}</p>
            <input ref={fileRef} type="file" accept="image/*" hidden onChange={upload} />
            <div className="form-actions">
              <button type="button" className="btn ghost sm" onClick={() => fileRef.current?.click()}>{me.photo_url ? "Change photo" : "Add a photo of yourself"}</button>
              {me.photo_url && <button type="button" className="btn ghost sm" onClick={async () => { await people.removePhoto(token); refresh(); }}>Remove</button>}
            </div>
            <p className="fine">Use a clear photo of yourself. It is shrunk on your device, checked before others can see it, and can be removed any time.</p>
          </div>
        </div>
        <Field label="Display name"><input value={f.display_name} minLength={2} maxLength={40} onChange={(e) => setF({ ...f, display_name: e.target.value })} /></Field>
        <Field label="About you" hint={`${f.bio.length}/280`}><textarea rows={3} maxLength={280} value={f.bio} onChange={(e) => setF({ ...f, bio: e.target.value })} placeholder="What you like to do, and what you are here for." /></Field>
        <div className="tag-pick"><span className="muted">What you like</span>
          <div className="chips">{options?.activities.map((a) => <button type="button" key={a.key} className="chip" aria-pressed={f.interests.includes(a.key)} onClick={() => toggle("interests", a.key)}>{a.label}</button>)}</div>
        </div>
        <div className="tag-pick"><span className="muted">Languages you speak</span>
          <div className="chips">{options?.languages.map((l) => <button type="button" key={l} className="chip" aria-pressed={f.languages.includes(l)} onClick={() => toggle("languages", l)}>{l}</button>)}</div>
        </div>
        <div className="fields">
          <Field label="Gender (optional)" hint="Shown on your profile if you choose one. People searching by gender only see those who shared it.">
            <select value={f.gender} onChange={(e) => setF({ ...f, gender: e.target.value })}>
              <option value="">Prefer not to say</option>
              {options?.genders.map((g) => <option key={g} value={g}>{g}</option>)}
            </select>
          </Field>
          <div className="field">
            <span>Age</span>
            <label className="check"><input type="checkbox" checked={f.show_age} onChange={(e) => setF({ ...f, show_age: e.target.checked })} /><span>Show my age range ({me.age_band || "n/a"}) on my profile. Your exact age is never shown.</span></label>
          </div>
        </div>
        <div className="tag-pick"><span className="muted">Who can find me? (optional)</span>
          <div className="chips">
            {options?.genders.map((g) => <button type="button" key={g} className="chip" aria-pressed={f.audience_genders.includes(g)} onClick={() => toggle("audience_genders", g)}>only {g}</button>)}
            {options?.age_bands.map((a) => <button type="button" key={a} className="chip" aria-pressed={f.audience_ages.includes(a)} onClick={() => toggle("audience_ages", a)}>age {a}</button>)}
          </div>
          <small className="hint">Leave empty to be found by everyone. If you limit it, only people who match can see your profile, find you in searches or ask to connect. People who have not shared that detail cannot pass the limit. For example, choose “only woman” to be visible to women only.</small>
        </div>
        <label className="check">
          <input type="checkbox" checked={f.visible} onChange={(e) => setF({ ...f, visible: e.target.checked })} />
          <span><b>Let other people find me.</b> Turn this off to hide your profile from everyone. Your chats stay.</span>
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        {note && <p className="notice" role="status">{note}</p>}
        <button className="btn primary" disabled={busy}>Save profile</button>
      </form>

      <div className="profile-side">
        <section className="card pad">
          <h2 className="card-title">Places I am going to</h2>
          {plans.length === 0 && <p className="muted">None yet. Open <b>Tonight</b>, pick a club or bar, and tap “I'm going”.</p>}
          <ul className="plain-list">
            {plans.map((p) => (
              <li key={p.id}><span><b>{p.place_name}</b><small>{longDate(p.day)}</small></span>
                <button className="linkbtn danger" onClick={async () => { await people.unattend(token, p.id); refresh(); }}>Cancel</button></li>
            ))}
          </ul>
        </section>
        {blocked.length > 0 && (
          <section className="card pad">
            <h2 className="card-title">People I blocked</h2>
            <ul className="plain-list">
              {blocked.map((b) => <li key={b.id}><span>{b.display_name}</span><button className="linkbtn" onClick={async () => { await people.unblock(token, b.id); refresh(); }}>Unblock</button></li>)}
            </ul>
          </section>
        )}
        <section className="card pad safety-note">
          <h2 className="card-title">Staying safe</h2>
          <Rules rules={options?.rules} />
        </section>
        <section className="card pad">
          <h2 className="card-title">Account</h2>
          <div className="form-actions">
            <button className="btn ghost sm" onClick={signOut}>Sign out</button>
            <button className="btn ghost sm danger-btn" onClick={remove}>Delete my account and data</button>
          </div>
        </section>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- a single profile, opened from a match, alert or toast

function PersonModal({ id, onClose }) {
  const { token } = usePeople();
  const [person, setPerson] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setPerson(null);
    setError("");
    people.get(token, id).then((p) => alive && setPerson(p)).catch((e) => alive && setError(e.message));
    return () => { alive = false; };
  }, [token, id]);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <button className="panel-close" onClick={onClose} aria-label="Close">×</button>
        {error && <p className="error" role="alert">{error}</p>}
        {!error && !person && <p className="muted pad">Loading…</p>}
        {person && <PersonCard person={person} />}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- page

export default function People() {
  const { token, me } = usePeople();
  const [params, setParams] = useSearchParams();
  const tab = ["find", "inbox", "profile"].includes(params.get("tab")) ? params.get("tab") : "find";
  const personId = params.get("person");
  const closePerson = () => { const p = new URLSearchParams(params); p.delete("person"); setParams(p); };
  const goTab = (k) => { const p = new URLSearchParams(params); p.set("tab", k); setParams(p); };
  if (!token || !me) return token ? <div className="wrap page"><p className="muted">Loading…</p></div> : <Landing />;
  return (
    <div className="wrap page">
      <BackLink fallback="/" />
      <div className="page-head">
        <div>
          <div className="eyebrow">People</div>
          <h1 className="h2">Hi {me.display_name}, who do you want to meet?</h1>
          <p className="muted">Find people for an activity, see who is going to a place, and chat once you both agree.</p>
        </div>
        <div className="tabs-inline">
          {TABS.map(([k, l]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => goTab(k)}>{l}</button>)}
        </div>
      </div>
      {tab === "find" && <Find />}
      {tab === "inbox" && <Inbox openId={params.get("chat")} />}
      {tab === "profile" && <Profile />}
      {personId && <PersonModal id={personId} onClose={closePerson} />}
    </div>
  );
}
