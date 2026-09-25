import { Link, useLocation } from "react-router-dom";
import { useTrip } from "../state/TripContext.jsx";
import { useAlerts } from "../state/AlertsContext.jsx";
import { useNearby } from "../state/NearbyContext.jsx";
import { useAccountSync } from "../state/AccountSyncContext.jsx";
import Sheet from "./Sheet.jsx";

/** Everything that isn't one of the few main buttons, one tap away: on phones from "More" in the bottom bar, on
 * wider screens from "More" in the top tabs. Nothing is reachable only from the page footer. */
export function useMoreItems() {
  const { trip, savedTrips } = useTrip();
  const { unseen } = useAlerts();
  const { prefs } = useNearby();
  const sync = useAccountSync();
  return [
    ...(trip ? [["/trips", "🗂️", "My trips", savedTrips.length ? `${savedTrips.length} saved` : null]] : []),
    ...(trip ? [["/stays", "🏨", "Stays", "Compare stays for this trip"], ["/explore", "🧭", "Explore", "Places and food on a map"]] : []),
    ["/people", "👥", "People", "Meet travelers going where you go"],
    ["/nearby", "📍", "Nearby", prefs.enabled ? "Live around you now" : "What's good around you"],
    ["/alerts", "🔔", "Radar", unseen.length ? `${unseen.length} new` : "Deals and matches as they appear"],
    ["/trips", "☁️", sync?.signedIn ? "Account" : "Sign in", sync?.signedIn ? `Trips on every device · ${sync.me.email}` : "Keep your trips on every device"],
    ["/partners", "🏢", "For businesses", "List your deals, check vouchers in"],
    ["/credits", "©️", "Credits", "Photo licences and data sources"],
  ].filter((item, i, all) => all.findIndex((x) => x[0] === item[0] && x[2] === item[2]) === i);
}

export default function MoreMenu({ open, onClose }) {
  const items = useMoreItems();
  const { pathname } = useLocation();
  return (
    <Sheet open={open} onClose={onClose} title="More" wide>
      <nav className="more-grid" aria-label="More">
        {items.map(([to, icon, label, hint]) => (
          <Link key={`${to}-${label}`} to={to} className={`more-tile ${pathname === to ? "on" : ""}`} onClick={onClose}>
            <span className="more-icon" aria-hidden="true">{icon}</span>
            <b>{label}</b>
            {hint && <small>{hint}</small>}
          </Link>
        ))}
      </nav>
    </Sheet>
  );
}
