import { useMemo } from "react";

const REGION_LABEL = { Europe: "Europe", Americas: "The Americas", Asia: "Asia and the Middle East", Oceania: "Australia" };

/** A native dropdown of all destinations, grouped by region. */
export default function DestSelect({ value, onChange, destinations, exclude, id }) {
  const groups = useMemo(() => {
    const by = {};
    destinations.forEach((d) => (by[d.region] ||= []).push(d));
    Object.values(by).forEach((list) => list.sort((a, b) => a.city.localeCompare(b.city)));
    return by;
  }, [destinations]);

  return (
    <select id={id} value={value} onChange={(e) => onChange(e.target.value)} disabled={!destinations.length}>
      {!destinations.length && <option value={value}>{value || "Loading…"}</option>}
      {Object.entries(groups).map(([region, list]) => (
        <optgroup key={region} label={REGION_LABEL[region] || region}>
          {list.map((d) => (
            <option key={d.code} value={d.code} disabled={d.code === exclude}>
              {d.city}, {d.country} ({d.code})
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}
