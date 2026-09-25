import { useEffect, useState } from "react";
import { useTrip } from "../state/TripContext.jsx";
import { INTERESTS } from "../lib/constants";
import { PLACE_TYPE_LABEL } from "../lib/profile";
import Sheet from "./Sheet.jsx";

const MAX_PLACE_TYPES = 14; // the planner's own limit

/** Change what the trip is tuned to: interests (they rank stays, ideas and deals, and decide which pop-ups count as
 * "matches what you like") and kinds of places to find (which real places are searched for). Saving searches the same
 * trip again, keeping the day plan and, when still offered, the chosen flight and stay. */
export default function InterestsSheet({ open, onClose, say }) {
  const { trip, replanTrip } = useTrip();
  const [interests, setInterests] = useState([]);
  const [types, setTypes] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (open && trip) {
      setInterests(trip.req.interests || []);
      setTypes(trip.req.place_types || []);
      setError("");
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!trip) return null;
  const same = (a, b) => [...a].sort().join() === [...b].sort().join();
  const unchanged = same(interests, trip.req.interests || []) && same(types, trip.req.place_types || []);
  const flip = (list, set, k, max = 99) => set(list.includes(k) ? list.filter((x) => x !== k) : list.length < max ? [...list, k] : list);

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      const kept = await replanTrip({ interests, place_types: types });
      if (!kept) throw new Error("Could not search again.");
      onClose();
      say?.("Interests saved. Stays, ideas and deals are re-ranked for you");
    } catch (e) {
      setError(e.message || "Something went wrong. Nothing was changed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet
      open={open}
      onClose={busy ? () => {} : onClose}
      wide
      title="What you like"
      subtitle={<span className="muted">Saved with this trip on this device. They rank your stays, ideas and deals, and pick which pop-ups you see</span>}
      footer={
        <button type="button" className="btn primary full" disabled={busy || unchanged} onClick={save}>
          {busy ? "Re-ranking…" : unchanged ? "No changes" : "Save and re-rank"}
        </button>
      }
    >
      <div className="slot-label">Interests</div>
      <div className="chips">
        {INTERESTS.map(([k, label]) => (
          <button key={k} type="button" className="chip" aria-pressed={interests.includes(k)} onClick={() => flip(interests, setInterests, k)}>{label}</button>
        ))}
      </div>
      <div className="slot-label">Kinds of places to find</div>
      <div className="chips">
        {Object.entries(PLACE_TYPE_LABEL).map(([k, label]) => (
          <button key={k} type="button" className="chip" aria-pressed={types.includes(k)} onClick={() => flip(types, setTypes, k, MAX_PLACE_TYPES)}>{label}</button>
        ))}
      </div>
      <ul className="tp-notes">
        <li>Your day plan stays as it is; your flight and stay are kept when still offered.</li>
        <li>Deals are ranked by match, real discount and distance, never by who pays.</li>
      </ul>
      {error && <p className="error" role="alert">{error}</p>}
    </Sheet>
  );
}
