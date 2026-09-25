import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAlerts } from "../state/AlertsContext.jsx";
import { usePeople } from "../state/PeopleContext.jsx";
import { useTrip } from "../state/TripContext.jsx";
import AlertCard from "../components/AlertCard.jsx";
import BackLink from "../components/BackLink.jsx";
import InterestsSheet from "../components/InterestsSheet.jsx";
import { TAG_LABEL } from "../lib/constants";

const TABS = [["all", "Everything"], ["deal", "Deals"], ["person", "People"], ["message", "Messages"]];

export default function Alerts() {
  const { alerts, settings, setSettings, status, refresh, markSeen, seen, rss } = useAlerts();
  const { token } = usePeople();
  const { trip, cityName, form } = useTrip();
  const [tab, setTab] = useState("all");
  const [likesOpen, setLikesOpen] = useState(false);
  const [likesNote, setLikesNote] = useState("");
  const [perm, setPerm] = useState(typeof Notification === "undefined" ? "unsupported" : Notification.permission);
  const city = cityName(trip?.req.destination || form.destination);

  const fresh = useRef(new Set());
  useEffect(() => {
    alerts.forEach((a) => !seen.has(a.id) && fresh.current.add(a.id));   // remember what was new when you arrived
    markSeen(alerts.map((a) => a.id));
  }, [alerts.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const shown = alerts.filter((a) => tab === "all" || a.kind === tab || (tab === "person" && a.kind === "request") || (tab === "message" && a.kind === "message"));
  const countOf = (k) => alerts.filter((a) => (k === "all" ? true : a.kind === k || (k === "person" && a.kind === "request"))).length;

  const enableDevice = async () => {
    if (settings.notify) return setSettings({ notify: false });
    const p = Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
    setPerm(p);
    setSettings({ notify: p === "granted" });
  };

  return (
    <div className="wrap page">
      <BackLink fallback="/" />
      <div className="page-head">
        <div>
          <div className="eyebrow">Radar</div>
          <h1 className="h2">Hot right now {trip ? `for your trip to ${city}` : `in ${city}`}</h1>
          <p className="muted">Deals that fit what you like, people who want the same as you, and messages, the moment they appear.</p>
          <p className="radar-likes">
            Matched to {(trip?.req.interests || form.interests).length ? (trip?.req.interests || form.interests).map((k) => TAG_LABEL[k] || k).join(", ") : "no interests yet"}
            {trip ? <> · <button type="button" className="linkbtn" onClick={() => setLikesOpen(true)}>change what you like</button></>
              : <> · <Link to="/">set them on the search form</Link></>}
          </p>
          {likesNote && <p className="notice ok-notice">{likesNote}</p>}
        </div>
        <button className="btn ghost" onClick={refresh}>↻ Check now</button>
      </div>

      <section className="card pad radar-settings">
        <div className="switch-grid">
          <label className="check"><input type="checkbox" checked={settings.deals} onChange={(e) => setSettings({ deals: e.target.checked })} /><span><b>Deals</b> on my trip or near me</span></label>
          <label className="check"><input type="checkbox" checked={settings.people} onChange={(e) => setSettings({ people: e.target.checked })} /><span><b>People</b>: matches, requests and messages{!token && " (sign in on the People page)"}</span></label>
          <label className="check"><input type="checkbox" checked={settings.notify} disabled={perm === "unsupported" || perm === "denied"} onChange={enableDevice} /><span><b>Notify this device</b>{perm === "denied" ? " (blocked in browser settings)" : " while the app is open. Up to 3 a day, never at night."}</span></label>
        </div>
        <div className="fields">
          <label className="field">Only deals at least
            <select value={settings.min_discount} onChange={(e) => setSettings({ min_discount: Number(e.target.value) })}>
              {[0, 10, 20, 30, 40, 50].map((v) => <option key={v} value={v}>{v}% off</option>)}
            </select>
          </label>
          <label className="field">Around my location, within
            <select value={settings.radius_m} onChange={(e) => setSettings({ radius_m: Number(e.target.value) })}>
              {[[1000, "1 km"], [3000, "3 km"], [5000, "5 km"], [10000, "10 km"], [25000, "25 km"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
        </div>
        <p className="fine">
          Deals follow your trip if you have one, and your live location if you switched on <Link to="/nearby">Nearby</Link>. Location is never stored.
          Prefer a feed reader? <a href={rss} target="_blank" rel="noreferrer">Subscribe to the RSS feed for {city} ↗</a>
        </p>
      </section>

      <div className="tabs-inline radar-tabs">
        {TABS.map(([k, l]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l} {countOf(k) > 0 && <em>{countOf(k)}</em>}</button>)}
      </div>

      {status === "loading" && <p className="muted">Scanning…</p>}
      {status === "error" && <p className="error">Could not check for alerts just now. It will retry.</p>}
      {status === "off" && <p className="notice">Alerts are switched off. Turn on Deals or People above.</p>}
      {status === "ok" && shown.length === 0 && (
        <div className="card pad empty">
          <b>Nothing hot right now.</b>
          <p className="muted">We keep watching. Try a lower discount, a wider radius, or plan a trip so deals can follow your dates.</p>
          <Link to="/" className="btn primary sm">Plan a trip</Link>
        </div>
      )}
      <div className="alert-grid">
        {shown.map((a) => <div key={a.id} className={fresh.current.has(a.id) ? "is-new" : ""}><AlertCard a={a} /></div>)}
      </div>
      <InterestsSheet open={likesOpen} onClose={() => setLikesOpen(false)} say={setLikesNote} />
    </div>
  );
}
