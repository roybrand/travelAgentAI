import { useCallback, useEffect, useState } from "react";
import { admin as api, adminPeople } from "../api";
import DealCard from "../components/DealCard.jsx";

const KEY = "wf.admin.v1";
const read = () => {
  try {
    return sessionStorage.getItem(KEY) || "";
  } catch {
    return "";
  }
};
const write = (v) => {
  try {
    if (v) sessionStorage.setItem(KEY, v);
    else sessionStorage.removeItem(KEY);
  } catch {
    /* storage may be unavailable */
  }
};

function Review({ deal, onApprove, onReject }) {
  const [reason, setReason] = useState("");
  const [rejecting, setRejecting] = useState(false);
  return (
    <div className="review">
      <DealCard deal={{ ...deal, match: [], why: [] }} preview />
      <div className="review-side">
        <p><b>{deal.partner_name}</b><br /><small>{deal.partner_email}</small></p>
        {deal.flags.length > 0 && (
          <ul className="flags">{deal.flags.map((f) => <li key={f}>{f}</li>)}</ul>
        )}
        <p className="fine">Check: is the offer real, is the usual price genuine, is the photo theirs, do the terms make sense?</p>
        {!rejecting ? (
          <div className="form-actions">
            <button className="btn primary sm" onClick={onApprove}>Approve</button>
            <button className="btn ghost sm" onClick={() => setRejecting(true)}>Reject…</button>
          </div>
        ) : (
          <div className="reject-box">
            <textarea rows={3} maxLength={300} placeholder="Reason shown to the business (at least 5 characters)" value={reason} onChange={(e) => setReason(e.target.value)} />
            <div className="form-actions">
              <button className="btn primary sm" disabled={reason.trim().length < 5} onClick={() => onReject(reason.trim())}>Send rejection</button>
              <button className="btn ghost sm" onClick={() => setRejecting(false)}>Back</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/** Photos are behind no header, but the address is unguessable; this simply shows it. */
function AuthImage({ src, alt }) {
  return <img className="review-photo" src={src} alt={alt} />;
}

export default function Admin() {
  const [token, setToken] = useState(read);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(null);
  const [partners, setPartners] = useState([]);
  const [photos, setPhotos] = useState([]);
  const [reports, setReports] = useState([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!token) return;
    try {
      const [p, q, ph, rp] = await Promise.all([api.pending(token), api.partners(token), adminPeople.photos(token), adminPeople.reports(token)]);
      setPending(p.deals);
      setPartners(q.partners);
      setPhotos(ph.photos);
      setReports(rp.reports);
      setError("");
    } catch (e) {
      setPending(null);
      setError(e.message);
      if (e.status === 401) {
        write("");
        setToken("");
      }
    }
  }, [token]);
  useEffect(() => void load(), [load]);

  const act = async (fn) => {
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e.message);
    }
  };

  if (!token) {
    return (
      <div className="wrap page narrow">
        <div className="eyebrow">Moderation</div>
        <h1 className="h2">Admin sign-in</h1>
        <form className="card pad auth" onSubmit={(e) => { e.preventDefault(); write(draft); setToken(draft); }}>
          <label className="field">Admin token
            <input type="password" value={draft} onChange={(e) => setDraft(e.target.value)} autoComplete="off" required />
          </label>
          {error && <p className="error" role="alert">{error}</p>}
          <button className="btn primary full">Continue</button>
          <p className="fine">The token is the ADMIN_TOKEN value in backend/.env. It is kept only for this browser tab.</p>
        </form>
      </div>
    );
  }

  return (
    <div className="wrap page">
      <div className="page-head">
        <div>
          <div className="eyebrow">Moderation</div>
          <h1 className="h2">Deals waiting for review{pending ? ` (${pending.length})` : ""}</h1>
        </div>
        <button className="btn ghost" onClick={() => { write(""); setToken(""); }}>Sign out</button>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {pending?.length === 0 && <div className="card pad empty"><b>Nothing to review.</b><p className="muted">New and edited deals appear here.</p></div>}
      <div className="review-list">
        {pending?.map((d) => (
          <Review key={d.id} deal={d} onApprove={() => act(() => api.approve(token, d.id))} onReject={(r) => act(() => api.reject(token, d.id, r))} />
        ))}
      </div>

      <section className="card pad">
        <h2 className="card-title">People: profile photos to review ({photos.length})</h2>
        {photos.length === 0 && <p className="muted">No photos are waiting.</p>}
        <div className="photo-review">
          {photos.map((p) => (
            <div key={p.user_id} className="card">
              <AuthImage token={token} src={p.photo_url} alt={`Photo from ${p.display_name}`} />
              <b>{p.display_name}</b>
              <div className="form-actions">
                <button className="btn primary sm" onClick={() => act(() => adminPeople.approvePhoto(token, p.user_id))}>Approve</button>
                <button className="btn ghost sm" onClick={() => act(() => adminPeople.rejectPhoto(token, p.user_id))}>Reject</button>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="card pad">
        <h2 className="card-title">People: open reports ({reports.length})</h2>
        {reports.length === 0 && <p className="muted">No open reports.</p>}
        <div className="table-wrap">
          <table className="table">
            <tbody>
              {reports.map((r) => (
                <tr key={r.id}>
                  <td><b>{r.target_name}</b><small>{r.reason} · {r.open_against} open against this person</small>{r.detail && <small>“{r.detail}”</small>}{r.message && <small>Message: “{r.message}”</small>}</td>
                  <td className="row-actions">
                    <button className="linkbtn" onClick={() => act(() => adminPeople.resolve(token, r.id, false))}>Dismiss</button>
                    <button className="linkbtn danger" onClick={() => window.confirm(`Ban ${r.target_name}?`) && act(() => adminPeople.resolve(token, r.id, true))}>Ban</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card pad">
        <h2 className="card-title">Partners</h2>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Business</th><th>Type</th><th>Deals</th><th>Shown</th><th>Clicks</th><th>Status</th><th /></tr></thead>
            <tbody>
              {partners.map((p) => (
                <tr key={p.id}>
                  <td><b>{p.name}</b><small>{p.email}</small></td>
                  <td>{p.business_type}</td>
                  <td>{p.deals}</td>
                  <td>{p.impressions}</td>
                  <td>{p.clicks}</td>
                  <td><span className={`src-badge ${p.status === "active" ? "ok" : "bad"}`}>{p.status}</span></td>
                  <td className="row-actions">
                    <button className="linkbtn" onClick={() => act(() => api.setStatus(token, p.id, p.status === "active" ? "suspended" : "active"))}>
                      {p.status === "active" ? "Suspend" : "Reinstate"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
