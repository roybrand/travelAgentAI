import { useState } from "react";

/** A small "change my password" form, shared by the People profile and the Partners dashboard. `onChange`
 * calls the right API with (current, next); `onDone` runs after success (both accounts sign out everywhere,
 * including here, so the caller should redirect to sign-in). */
export default function ChangePasswordForm({ onChange, onDone }) {
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (!open) return <button type="button" className="linkbtn" onClick={() => setOpen(true)}>Change password</button>;

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (next !== confirm) return setError("The new passwords do not match.");
    setBusy(true);
    try {
      await onChange(current, next);
      onDone();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <form className="change-password" onSubmit={submit}>
      <label className="field">Current password<input type="password" required value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" /></label>
      <label className="field">New password<input type="password" required minLength={10} value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" /></label>
      <label className="field">Confirm new password<input type="password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" /></label>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="form-actions">
        <button className="btn primary sm" disabled={busy}>{busy ? "Changing…" : "Save new password"}</button>
        <button type="button" className="btn ghost sm" onClick={() => setOpen(false)} disabled={busy}>Cancel</button>
      </div>
      <p className="fine">This signs you out everywhere, including here. Sign back in with your new password.</p>
    </form>
  );
}
