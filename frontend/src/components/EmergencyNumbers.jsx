import { useEffect, useState } from "react";
import { fetchEmergencyNumbers } from "../api";

const STORE_KEY = "wf.emergencyCountry";
const remembered = () => { try { return localStorage.getItem(STORE_KEY) || ""; } catch { return ""; } };
const remember = (c) => { try { localStorage.setItem(STORE_KEY, c); } catch { /* storage blocked: just don't remember */ } };

/** Local emergency numbers for where the traveler is. The country comes from a position (matched against the
 * built-in city list on our own server, never a map service), else the last country shown, else the person picks. */
export default function EmergencyNumbers({ lat, lng }) {
  const [picked, setPicked] = useState("");
  const [data, setData] = useState(null);

  useEffect(() => {
    const params = picked ? { country: picked } : lat != null && lng != null ? { lat, lng } : { country: remembered() };
    fetchEmergencyNumbers(params).then((r) => { setData(r); if (r.country) remember(r.country); }).catch(() => {});
  }, [picked, lat, lng]);

  if (!data) return null;
  const n = data.numbers;
  const tel = (num) => <a href={`tel:${num}`} className="emergency-num">{num}</a>;
  const direct = n && [["Police", n.police], ["Ambulance", n.ambulance], ["Fire", n.fire], ["Tourist police", n.tourist]]
    .filter(([, num]) => num && num !== n.general);

  return (
    <div className="emergency" role="note" aria-label="Emergency numbers">
      <div className="emergency-head">
        <b>🚨 Emergency{data.country ? ` in ${data.country}` : ""}</b>
        {n?.general && tel(n.general)}
        <select aria-label="Country" value={data.country || ""} onChange={(e) => setPicked(e.target.value)}>
          {!data.country && <option value="">Choose a country</option>}
          {data.countries.map((c) => <option key={c}>{c}</option>)}
        </select>
      </div>
      {direct?.length > 0 && <div className="emergency-list">{direct.map(([label, num]) => <span key={label}>{label} {tel(num)}</span>)}</div>}
      <p className="fine">{data.note}</p>
    </div>
  );
}
