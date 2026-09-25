import { useCallback, useEffect, useState } from "react";
import { partner as api } from "../api";
import { PART_ICON, PART_LABEL } from "../lib/dayplan";
import { longDate } from "../lib/format";

const price = (n, cur) => new Intl.NumberFormat("en-GB", { style: "currency", currency: cur || "GBP", maximumFractionDigits: Number.isInteger(n) ? 0 : 2 }).format(n);
const STATUS = { confirmed: ["Booked", "live"], redeemed: ["Used", "estimate"], cancelled: ["Cancelled", "muted"] };
const payText = (r) => (r.pay === "now" ? "Paid in the app" : `Collect ${price(r.total, r.currency)} here`);

/** For the business: who's coming (never who they are; the voucher is the proof), and a check-in for vouchers
 * shown at the door. Travelers booked these as demo reservations through Wayfinder. */
export default function ReservationsPanel({ token }) {
  const [data, setData] = useState(null);
  const [code, setCode] = useState("");
  const [found, setFound] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.reservations(token).then(setData).catch((e) => setError(e.message));
  }, [token]);
  useEffect(() => {
    load();
    const t = setInterval(load, 30000); // new bookings arrive while the dashboard is open
    return () => clearInterval(t);
  }, [load]);

  const check = async (e) => {
    e?.preventDefault();
    setBusy(true);
    setError("");
    setFound(null);
    try {
      setFound(await api.checkVoucher(token, code.trim()));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  const redeem = async (ref) => {
    setBusy(true);
    setError("");
    try {
      const r = await api.redeem(token, ref);
      setFound((f) => (f && f.reference === ref ? { ...f, ...r, can_redeem: false, warnings: [], justUsed: true } : f));
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const list = data?.reservations || [];
  return (
    <section className="card pad reservations">
      <div className="card-head">
        <h2 className="card-title">Reservations</h2>
        <button type="button" className="linkbtn" onClick={load}>↻ Refresh</button>
      </div>
      {data && (
        <div className="stat-row compact">
          <div className="card stat"><b>{data.counts.today}</b><span>Coming today</span></div>
          <div className="card stat"><b>{data.counts.upcoming}</b><span>Upcoming</span></div>
          <div className="card stat"><b>{data.counts.used}</b><span>Vouchers used</span></div>
        </div>
      )}

      <form className="voucher-check" onSubmit={check}>
        <label className="field">
          <span>Check in a guest: type the voucher on their phone</span>
          <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="V-XXXXXXXX" maxLength={20} autoCapitalize="characters" spellCheck={false} />
        </label>
        <button className="btn primary" disabled={busy || code.trim().length < 4}>Check</button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}

      {found && (
        <div className={`voucher-result ${found.status}`}>
          <div className="voucher-head">
            <b>{found.quantity} × {found.title}</b>
            <span className={`src-badge ${STATUS[found.status][1]}`}>{found.justUsed ? "✓ Checked in" : STATUS[found.status][0]}</span>
          </div>
          <p className="muted">
            {longDate(found.date)}{found.part ? ` · ${PART_ICON[found.part]} ${PART_LABEL[found.part]}` : ""} · {found.voucher} · booking {found.reference}
          </p>
          <p className="voucher-pay">{found.status === "redeemed" && !found.justUsed ? "Already used." : payText(found)}</p>
          {found.warnings?.map((w) => <p key={w} className="notice">{w}</p>)}
          {found.can_redeem && <button type="button" className="btn primary" disabled={busy} onClick={() => redeem(found.reference)}>Mark as used</button>}
        </div>
      )}

      {list.length === 0 ? (
        <p className="muted">No reservations yet. When travelers book one of your deals, it shows up here with the day, time and how they pay.</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>When</th><th>Deal</th><th>Guests</th><th>Payment</th><th>Voucher</th><th>Status</th><th /></tr></thead>
            <tbody>
              {list.map((r) => {
                const [text, tone] = STATUS[r.status];
                return (
                  <tr key={r.reference} className={r.is_today ? "today-row" : ""}>
                    <td><b>{r.is_today ? "Today" : longDate(r.date)}</b>{r.part && <small>{PART_ICON[r.part]} {PART_LABEL[r.part]}</small>}</td>
                    <td>{r.title}</td>
                    <td>{r.quantity}</td>
                    <td>{r.pay === "now" ? "Paid in app" : `${price(r.total, r.currency)} at the door`}</td>
                    <td><code>{r.voucher || "–"}</code></td>
                    <td><span className={`src-badge ${tone}`}>{text}</span></td>
                    <td>{r.status === "confirmed" && <button type="button" className="linkbtn" disabled={busy} onClick={() => redeem(r.reference)}>Check in</button>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="fine">You never see who booked: only the voucher, the day and how many. Demo: no money moves through Wayfinder, even for "Paid in the app".</p>
    </section>
  );
}
