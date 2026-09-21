import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import Photo from "./Photo";

const STEPS = [
  ["Searching flights", "flights MCP server"],
  ["Comparing stays", "hotels MCP server, matched to your interests"],
  ["Reading the destination guide", "guides MCP server: season, places, adventures"],
  ["Ranking every combination", "price, rating, comfort, budget fit"],
  ["Building your trip", "pros, cons and the best time to go"],
];

export default function PlanningOverlay({ photo }) {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((n) => Math.min(n + 1, STEPS.length - 1)), 460);
    return () => clearInterval(t);
  }, []);
  return (
    <motion.div className="overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <Photo k={photo} className="overlay-bg" />
      <div className="overlay-scrim" />
      <div className="overlay-card">
        <div className="spinner" />
        <h2>Your AI agent is on it</h2>
        <ul>
          {STEPS.map(([title, sub], n) => (
            <li key={title} className={n < i ? "done" : n === i ? "active" : ""}>
              <span className="tick" />
              <div>
                <b>{title}</b>
                <small>{sub}</small>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </motion.div>
  );
}
