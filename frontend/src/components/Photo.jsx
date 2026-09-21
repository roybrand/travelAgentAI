import { useState } from "react";
import credits from "../data/photoCredits.json";

const hueOf = (s = "") => [...s].reduce((a, c) => (a * 31 + c.charCodeAt(0)) % 360, 7);
const clean = (s) => s.replace(/^(this (photo|image) was taken by|photo by|image by)\s*/i, "");
const shorten = (s, n = 26) => ((s = clean(s)).length > n ? s.slice(0, n - 1) + "…" : s);

/**
 * Photo with a graceful gradient fallback and proper licence credit.
 * Use `k` for a bundled photo key, or `src` + `info` ({author, license, source}) for a live Wikimedia photo.
 */
export default function Photo({ k, src, info, alt = "", className = "", credit = false, children, style }) {
  const [failed, setFailed] = useState(false);
  const c = info || credits[k];
  const url = src || (k ? `/photos/${k}.jpg` : null);
  const h = hueOf(k || src || alt);
  return (
    <div
      className={`photo ${className}`}
      style={{ background: `linear-gradient(135deg, hsl(${h} 45% 24%), hsl(${(h + 50) % 360} 50% 12%))`, ...style }}
    >
      {url && !failed && <img src={url} alt={alt} loading="lazy" decoding="async" onError={() => setFailed(true)} />}
      {children}
      {credit && c && !failed && url && (
        <a
          className="credit"
          href={c.source}
          target="_blank"
          rel="noreferrer"
          onClick={(e) => e.stopPropagation()}
          title={`${c.title || ""} ${c.author} ${c.license}`.trim()}
        >
          Photo: {shorten(c.author)} · {c.license}
        </a>
      )}
    </div>
  );
}
