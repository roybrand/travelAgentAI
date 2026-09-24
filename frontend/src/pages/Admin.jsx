import { useCallback, useEffect, useState } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { admin as api, adminPeople } from "../api";
import DealCard from "../components/DealCard.jsx";
import BackLink from "../components/BackLink.jsx";

const CHART_TOOLTIP = { background: "#0d1826", border: "1px solid #24364d", borderRadius: 10 };
const CHART_ITEM = { color: "#e8eef6" };
const AXIS_MUTED = { fill: "#8ea2b9", fontSize: 11 };

function DailyChart({ title, data, color }) {
  const gid = `an-${title.replace(/[^a-zA-Z0-9]/g, "")}`;
  return (
    <div className="card pad">
      <h3 className="card-title">{title}</h3>
      <ResponsiveContainer width="100%" height={140}>
        <AreaChart data={data} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.35} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="day" tickLine={false} axisLine={false} tick={AXIS_MUTED} tickFormatter={(d) => d.slice(5)} minTickGap={24} />
          <YAxis hide allowDecimals={false} />
          <Tooltip cursor={{ stroke: "#24364d" }} contentStyle={CHART_TOOLTIP} itemStyle={CHART_ITEM} labelStyle={AXIS_MUTED} />
          <Area type="monotone" dataKey="count" name="Count" stroke={color} strokeWidth={2} fill={`url(#${gid})`} dot={false} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

/** A plain HTML/CSS bar list rather than a chart library bar chart: simpler, and every step -- including a
 * genuine zero -- always shows its own row, its own bar (even a zero-width one) and its own number. */
function FunnelChart({ title, steps }) {
  const max = Math.max(1, ...steps.map((s) => s.count));
  return (
    <div className="card pad">
      <h3 className="card-title">{title}</h3>
      <div className="funnel-rows">
        {steps.map((s) => (
          <div className="funnel-row" key={s.label}>
            <span className="funnel-label">{s.label}</span>
            <span className="funnel-bar-track">
              <span className="funnel-bar" style={{ width: `${(s.count / max) * 100}%` }} />
            </span>
            <span className="funnel-count">{s.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Analytics({ token }) {
  const [data, setData] = useState(null);
  const [days, setDays] = useState(30);
  const [error, setError] = useState("");

  useEffect(() => {
    api.analytics(token, days).then(setData).catch((e) => setError(e.message));
  }, [token, days]);

  return (
    <section className="analytics-section">
      <div className="page-head">
        <div>
          <div className="eyebrow">Investor view</div>
          <h2 className="h2">Analytics</h2>
        </div>
        <div className="chips">
          {[7, 30, 90].map((d) => <button key={d} type="button" className="chip" aria-pressed={days === d} onClick={() => setDays(d)}>{d} days</button>)}
        </div>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {data && (
        <>
          <div className="stat-row analytics-kpis">
            <div className="card stat"><b>{data.kpis.people_registered}</b><span>People registered</span></div>
            <div className="card stat"><b>{data.kpis.partners_registered}</b><span>Businesses registered</span></div>
            <div className="card stat"><b>{data.kpis.deals_submitted}</b><span>Deals submitted</span></div>
            <div className="card stat"><b>{data.kpis.connections_requested}</b><span>Connections requested</span></div>
            <div className="card stat"><b>{data.kpis.messages_sent}</b><span>Messages sent</span></div>
            <div className="card stat"><b>{data.kpis.reports_filed}</b><span>Reports filed</span></div>
            <div className="card stat"><b>{data.kpis.demo_bookings ?? 0}</b><span>Demo bookings</span></div>
          </div>
          <div className="analytics-grid">
            <DailyChart title="People registrations / day" data={data.daily.people_registered} color="#2dd4bf" />
            <DailyChart title="Messages sent / day" data={data.daily.messages_sent} color="#f5c76a" />
          </div>
          <div className="analytics-grid">
            <FunnelChart title="People funnel" steps={data.people_funnel} />
            <FunnelChart title="Partner funnel" steps={data.partner_funnel} />
            {data.booking_funnel && <FunnelChart title="Booking funnel (demo)" steps={data.booking_funnel} />}
          </div>
          <p className="fine">
            Self-hosted: built entirely from events already in the activity log. No vendor, no cookies, no cross-site tracking. There is no
            visit-level tracking, so each funnel step is its own real count in the window, not a strict per-visitor conversion rate.
          </p>
        </>
      )}
    </section>
  );
}

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
      <BackLink fallback="/" />
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
      <BackLink fallback="/" />
      <div className="page-head">
        <div>
          <div className="eyebrow">Moderation</div>
          <h1 className="h2">Deals waiting for review{pending ? ` (${pending.length})` : ""}</h1>
        </div>
        <button className="btn ghost" onClick={() => { write(""); setToken(""); }}>Sign out</button>
      </div>

      <Analytics token={token} />

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
                  <td>
                    <b>{r.target_name}</b>{r.target_under_review && <span className="src-badge warn">Auto-hidden</span>}
                    <small>{r.reason} · {r.open_against} open against this person</small>{r.detail && <small>“{r.detail}”</small>}{r.message && <small>Message: “{r.message}”</small>}
                  </td>
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
