import { useState } from "react";
import { people } from "../api";
import { usePeople } from "../state/PeopleContext.jsx";
import { useAccountSync } from "../state/AccountSyncContext.jsx";
import Sheet from "./Sheet.jsx";

const ago = (iso) => {
  if (!iso) return "";
  const s = Math.round((Date.now() - new Date(iso)) / 1000);
  return s < 60 ? "just now" : s < 3600 ? `${Math.round(s / 60)} min ago` : new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

/** Sign in, or create the one Wayfinder account (the same one People uses), so trips follow you to every device. */
export function AccountSheet({ open, onClose }) {
  const { signIn } = usePeople();
  const [mode, setMode] = useState("login");
  const [f, setF] = useState({ email: "", password: "", display_name: "", birth_year: "", agreed: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = mode === "login"
        ? await people.login({ email: f.email, password: f.password })
        : await people.register({ email: f.email, password: f.password, display_name: f.display_name, birth_year: Number(f.birth_year), agreed: f.agreed });
      signIn(r.token);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open={open} onClose={busy ? () => {} : onClose} title={mode === "login" ? "Sign in to Wayfinder" : "Create your Wayfinder account"}
      subtitle={<span className="muted">Keeps your trips and bookings on every device. The same account works for People</span>}>
      <form className="acct-form" onSubmit={submit}>
        <div className="tabs-inline">
          <button type="button" className={mode === "login" ? "on" : ""} onClick={() => setMode("login")}>Sign in</button>
          <button type="button" className={mode === "register" ? "on" : ""} onClick={() => setMode("register")}>Create account</button>
        </div>
        {mode === "register" && (
          <label className="field"><span>Your name</span><input required minLength={2} maxLength={40} value={f.display_name} onChange={set("display_name")} autoComplete="name" /></label>
        )}
        <label className="field"><span>Email</span><input required type="email" value={f.email} onChange={set("email")} autoComplete="email" /></label>
        <label className="field"><span>Password</span><input required type="password" minLength={mode === "register" ? 10 : 1} value={f.password} onChange={set("password")} autoComplete={mode === "login" ? "current-password" : "new-password"} /></label>
        {mode === "register" && (
          <>
            <label className="field"><span>Year of birth</span><input required type="number" min={1900} max={new Date().getFullYear() - 18} value={f.birth_year} onChange={set("birth_year")} /><small className="hint">Wayfinder is for adults. It's never shown to anyone.</small></label>
            <label className="check"><input type="checkbox" checked={f.agreed} onChange={set("agreed")} /><span>I'm 18 or older and accept the terms and the community rules</span></label>
          </>
        )}
        {error && <p className="error" role="alert">{error}</p>}
        <button className="btn primary full" disabled={busy || (mode === "register" && !f.agreed)}>{busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}</button>
        <p className="fine">Names you type at checkout stay on this device; they're never saved with your account.</p>
      </form>
    </Sheet>
  );
}

/** Where your trips live: this device only, or your account on every device. */
export default function AccountPanel({ compact = false }) {
  const { signOut } = usePeople();
  const sync = useAccountSync();
  const [open, setOpen] = useState(false);

  if (!sync?.signedIn) {
    return (
      <div className={`acct-panel off ${compact ? "compact" : ""}`}>
        <span>📱 Your trips are on <b>this device only</b>. Clearing the browser or changing phone loses them.</span>
        <button type="button" className="btn primary sm" onClick={() => setOpen(true)}>Keep them on every device</button>
        <AccountSheet open={open} onClose={() => setOpen(false)} />
      </div>
    );
  }
  const text = sync.state === "syncing" ? "Syncing…" : sync.state === "error" ? `Not synced: ${sync.error}` : `Synced ${ago(sync.at)}`;
  return (
    <div className={`acct-panel on ${sync.state} ${compact ? "compact" : ""}`}>
      <span>☁️ Kept with <b>{sync.me.email}</b> on every device · <span className="muted">{text}</span></span>
      <span className="acct-actions">
        <button type="button" className="linkbtn" onClick={sync.syncNow} disabled={sync.state === "syncing"}>Sync now</button>
        {!compact && <button type="button" className="linkbtn" onClick={signOut} title="Your trips stay on this device and in your account">Sign out</button>}
      </span>
    </div>
  );
}
