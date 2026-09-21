import { SOURCE_MODE } from "../lib/constants";

/** Small pill saying where a piece of data came from: Live, Estimate, Demo. */
export default function SourceBadge({ mode, label, title }) {
  const m = SOURCE_MODE[mode] || SOURCE_MODE.demo;
  return (
    <span className={`src-badge ${m.tone}`} title={title}>
      {label || m.label}
    </span>
  );
}
