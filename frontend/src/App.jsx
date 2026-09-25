import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { checkHealth } from "./api";
import { useNearby } from "./state/NearbyContext.jsx";
import { useTrip } from "./state/TripContext.jsx";
import Home from "./pages/Home.jsx";
import Trip from "./pages/Trip.jsx";
import Book from "./pages/Book.jsx";
import Trips from "./pages/Trips.jsx";
import Stays from "./pages/Stays.jsx";
import Explore from "./pages/Explore.jsx";
import Credits from "./pages/Credits.jsx";
import Nearby from "./pages/Nearby.jsx";
import Deals from "./pages/Deals.jsx";
import Tonight from "./pages/Tonight.jsx";
import People from "./pages/People.jsx";
import Alerts from "./pages/Alerts.jsx";
import SafetyCheckin from "./pages/SafetyCheckin.jsx";
import { AlertBell, AlertToasts } from "./components/AlertBell.jsx";
import Partners from "./pages/Partners.jsx";
import Admin from "./pages/Admin.jsx";
import MoreMenu, { useMoreItems } from "./components/MoreMenu.jsx";
import { useAlerts } from "./state/AlertsContext.jsx";

function Header() {
  const { trip, resetSearch, savedTrips } = useTrip();
  const navigate = useNavigate();
  const { prefs } = useNearby();
  const live = prefs.enabled;
  const [online, setOnline] = useState(null);
  const [more, setMore] = useState(false);
  useEffect(() => {
    const run = () => checkHealth().then(setOnline);
    run();
    const t = setInterval(run, 30000);
    return () => clearInterval(t);
  }, []);
  return (
    <header className="topbar">
      <Link to="/" className="brand">
        <span className="logo">
          <svg viewBox="0 0 24 24" fill="#041014"><path d="M2 12.5 21 3l-6.5 18-3.2-7.6z" /></svg>
        </span>
        Wayfinder <small>AI</small>
      </Link>
      <nav className="tabs" aria-label="Sections">
        <NavLink to="/" end>Home</NavLink>
        {savedTrips.length > 0 && <NavLink to="/trips" end>My trips</NavLink>}
        {trip && (
          <>
            <NavLink to="/trip">Your trip</NavLink>
            <NavLink to="/stays">Stays</NavLink>
            <NavLink to="/explore">Explore</NavLink>
          </>
        )}
        <NavLink to="/tonight">Tonight</NavLink>
        <NavLink to="/people">People</NavLink>
        <NavLink to="/deals">Deals</NavLink>
        <NavLink to="/nearby">Nearby{live && <i className="live-dot" title="Live recommendations are on" />}</NavLink>
        <button type="button" className="tab-more" onClick={() => setMore(true)} aria-haspopup="dialog">More ▾</button>
      </nav>
      <MoreMenu open={more} onClose={() => setMore(false)} />
      {trip && (
        <button
          className="btn ghost sm new-search"
          title="Clear this trip and start a new search"
          onClick={() => {
            resetSearch();
            navigate("/");
          }}
        >
          ↺ New search
        </button>
      )}
      <AlertBell />
      <NavLink to="/partners" className="biz-link" title="For businesses: list your deals">For businesses</NavLink>
      <div className="pill" title="Backend status">
        <span className={`dot ${online === null ? "" : online ? "live" : "down"}`} />
        {online === null ? "Checking…" : online ? "Agents online" : "Backend unreachable"}
      </div>
    </header>
  );
}

/** The bar at the bottom of the screen on phones: five big, labelled buttons for what's used most, and More for the
 * rest (a sheet with every other part of the app). Always on screen, never at the end of a page. */
function BottomNav() {
  const { trip } = useTrip();
  const { unseen } = useAlerts();
  const { pathname } = useLocation();
  const [more, setMore] = useState(false);
  const moreItems = useMoreItems();
  const items = [
    ["/", "Home", "🏠", true],
    trip ? ["/trip", "Trip", "🧳", false] : ["/trips", "My trips", "🗂️", true],
    ["/tonight", "Tonight", "🌙", false],
    ["/deals", "Deals", "🏷️", false],
  ];
  const inMore = moreItems.some(([to]) => to === pathname) && !items.some(([to]) => to === pathname);
  return (
    <>
      <nav className="bottomnav" aria-label="Main">
        {items.map(([to, label, icon, end]) => (
          <NavLink key={to} to={to} end={end}>
            <span aria-hidden="true">{icon}</span>
            {label}
          </NavLink>
        ))}
        <button type="button" className={`bn-more ${inMore ? "active" : ""}`} onClick={() => setMore(true)} aria-haspopup="dialog">
          <span aria-hidden="true">☰</span>
          More
          {unseen.length > 0 && <i className="bn-badge">{unseen.length > 9 ? "9+" : unseen.length}</i>}
        </button>
      </nav>
      <MoreMenu open={more} onClose={() => setMore(false)} />
    </>
  );
}

/** A bar inside the pages of an open trip, so its parts are always one tap apart. */
function TripNav() {
  const { trip, cityName } = useTrip();
  const { pathname } = useLocation();
  if (!trip || !["/trip", "/stays", "/explore", "/book"].includes(pathname)) return null;
  return (
    <nav className="subnav" aria-label="This trip">
      <div className="wrap subnav-in">
        <span className="subnav-title">🧳 {cityName(trip.req.destination)}</span>
        <NavLink to="/trip">Itinerary</NavLink>
        <NavLink to="/stays">Stays</NavLink>
        <NavLink to="/explore">Explore</NavLink>
        <NavLink to="/book">Book</NavLink>
        <NavLink to="/tonight">Tonight</NavLink>
        <NavLink to="/deals">Deals</NavLink>
      </div>
    </nav>
  );
}

function Toasts() {
  const { toasts, dismiss } = useNearby();
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map(({ id, rec }) => (
        <Link key={id} to="/nearby" className="toast" onClick={() => dismiss(id)}>
          <b>📍 {rec.title}</b>
          <span>{rec.reason}</span>
        </Link>
      ))}
    </div>
  );
}

function Footer() {
  return (
    <footer className="footer">
      {/* Secondary links only: every main part of the app is in the top tabs or More (desktop) and the bottom bar (phones). */}
      <nav className="footer-nav" aria-label="Site">
        <Link to="/partners">For businesses</Link>
        <Link to="/credits">Credits</Link>
        <Link to="/admin">Admin</Link>
      </nav>
      <div>
        <b>Wayfinder AI</b> · LangGraph orchestration · MCP tool servers · FastAPI · React
      </div>
      <div className="footer-note">
        Prototype. Weather, sights, hotels and restaurants come from free public sources. Flight and stay prices are labelled
        estimates unless real offers are configured. Partner deals are set by the businesses and reviewed by us. Photos are openly
        licensed (<Link to="/credits">see credits</Link>). Run a business? <Link to="/partners">List your deals</Link>.
      </div>
    </footer>
  );
}

export default function App() {
  const location = useLocation();
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [location.pathname]);
  return (
    <div className="app">
      <Header />
      <TripNav />
      <AnimatePresence mode="wait">
        <motion.main
          key={location.pathname}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.28 }}
        >
          <Routes location={location}>
            <Route path="/" element={<Home />} />
            <Route path="/trip" element={<Trip />} />
            <Route path="/plan" element={<Navigate to="/trip" replace />} />
            <Route path="/book" element={<Book />} />
            <Route path="/trips" element={<Trips />} />
            <Route path="/stays" element={<Stays />} />
            <Route path="/explore" element={<Explore />} />
            <Route path="/nearby" element={<Nearby />} />
            <Route path="/deals" element={<Deals />} />
            <Route path="/tonight" element={<Tonight />} />
            <Route path="/people" element={<People />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/safety/:token" element={<SafetyCheckin />} />
            <Route path="/partners" element={<Partners />} />
            <Route path="/admin" element={<Admin />} />
            <Route path="/credits" element={<Credits />} />
            <Route path="*" element={<Home />} />
          </Routes>
        </motion.main>
      </AnimatePresence>
      <Toasts />
      <AlertToasts />
      <Footer />
      <BottomNav />
    </div>
  );
}
