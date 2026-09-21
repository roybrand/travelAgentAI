import { useState } from "react";
import { people } from "../api";
import { usePeople } from "../state/PeopleContext.jsx";

const hue = (s = "") => [...s].reduce((a, c) => (a * 31 + c.charCodeAt(0)) % 360, 11);

/** A photo when the person has an approved one, otherwise their initials. */
export function Avatar({ person, size = 56 }) {
  const [failed, setFailed] = useState(false);
  const initials = (person.display_name || "?").split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  return (
    <span className="avatar" style={{ width: size, height: size, background: `linear-gradient(135deg, hsl(${hue(person.display_name)} 50% 34%), hsl(${(hue(person.display_name) + 50) % 360} 55% 20%))`, fontSize: size * 0.38 }}>
      {person.photo_url && !failed ? <img src={person.photo_url} alt={`${person.display_name}'s photo`} onError={() => setFailed(true)} /> : initials}
    </span>
  );
}

/** Report or block from any card. Both are one tap away, because safety should never be hard to find. */
function SafetyMenu({ person, onDone }) {
  const { token, options } = usePeople();
  const [mode, setMode] = useState("");
  const [reason, setReason] = useState("harassment");
  const [detail, setDetail] = useState("");
  const [note, setNote] = useState("");

  const act = async (fn, msg) => {
    try {
      await fn();
      setNote(msg);
      setMode("");
      onDone?.();
    } catch (e) {
      setNote(e.message);
    }
  };

  if (note) return <p className="fine">{note}</p>;
  return (
    <div className="safety">
      {!mode && (
        <>
          <button className="linkbtn" onClick={() => setMode("report")}>Report</button>
          <button className="linkbtn danger" onClick={() => window.confirm(`Block ${person.display_name}? You will disappear from each other everywhere.`) && act(() => people.block(token, person.id), "Blocked.")}>Block</button>
        </>
      )}
      {mode === "report" && (
        <div className="report-box">
          <select value={reason} onChange={(e) => setReason(e.target.value)}>{(options?.report_reasons || ["other"]).map((r) => <option key={r}>{r}</option>)}</select>
          <textarea rows={2} maxLength={500} placeholder="What happened? (optional)" value={detail} onChange={(e) => setDetail(e.target.value)} />
          <div className="form-actions">
            <button className="btn primary sm" onClick={() => act(() => people.report(token, { user_id: person.id, reason, detail }), "Reported. A moderator will look at it. You can also block them.")}>Send report</button>
            <button className="btn ghost sm" onClick={() => setMode("")}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}

/** A person: who they are, what you share, and the ways to say hi. Nobody can message before the other accepts. */
export default function PersonCard({ person, extra, compact = false, showActions = true }) {
  const { token, options } = usePeople();
  const [note, setNote] = useState("");
  const [asking, setAsking] = useState(false);
  const [msg, setMsg] = useState("");
  const [state, setState] = useState("idle"); // idle | sending | sent | error
  const label = (k) => options?.activities.find((a) => a.key === k)?.label || k;

  const sayHi = async () => {
    setState("sending");
    try {
      const r = await people.connect(token, person.id, msg);
      setState("sent");
      setNote(r.status === "accepted" ? "You are connected. Open your Inbox to chat." : "Request sent. You can chat once they accept.");
    } catch (e) {
      setState("error");
      setNote(e.message);
    }
  };

  return (
    <article className={`card person ${compact ? "compact" : ""}`}>
      <Avatar person={person} size={compact ? 44 : 64} />
      <div className="person-main">
        <b>{person.display_name}{person.demo && <em className="demo-tag">demo</em>}</b>
        {person.bio && !compact && <p className="muted">{person.bio}</p>}
        <div className="facts-row">
          {person.shared?.map((t) => <span key={t} className="tag hit">★ {label(t)}</span>)}
          {!compact && person.interests?.filter((t) => !person.shared?.includes(t)).slice(0, 3).map((t) => <span key={t} className="tag">{label(t)}</span>)}
          {person.languages?.slice(0, 3).map((l) => <span key={l} className="tag">{l}</span>)}
        </div>
        {person.request && <p className="fine person-request">Looking for: “{person.request}” · {person.distance}</p>}
        {person.why?.length > 0 && <p className="fine">{person.why.join(" · ")}</p>}
        {extra}
        {showActions && token && (
          <div className="person-actions">
            {state === "idle" && !asking && <button className="btn primary sm" onClick={() => setAsking(true)}>Say hi</button>}
            {asking && state === "idle" && (
              <div className="hi-box">
                <input maxLength={200} placeholder="Add a short note (optional)" value={msg} onChange={(e) => setMsg(e.target.value)} />
                <button className="btn primary sm" onClick={sayHi}>Send request</button>
                <button className="btn ghost sm" onClick={() => setAsking(false)}>Cancel</button>
              </div>
            )}
            {note && <p className={state === "error" ? "err" : "fine"}>{note}</p>}
            <SafetyMenu person={person} />
          </div>
        )}
      </div>
    </article>
  );
}
