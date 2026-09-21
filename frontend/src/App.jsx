import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Link, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { checkHealth } from "./api";
import { useNearby } from "./state/NearbyContext.jsx";
import { useTrip } from "./state/TripContext.jsx";
import Home from "./pages/Home.jsx";
import Trip from "./pages/Trip.jsx";
import Stays from "./pages/Stays.jsx";
import Explore from "./pages/Explore.jsx";
import Credits from "./pages/Credits.jsx";
import Nearby from "./pages/Nearby.jsx";
import Deals from "./pages/Deals.jsx";
import Tonight from "./pages/Tonight.jsx";
import People from "./pages/People.jsx";
import Partners from "./pages/Partners.jsx";
import Admin from "./pages/Admin.jsx";

function Header() {
  const { trip, resetSearch } = useTrip();
  const navigate = useNavigate();
  const { prefs } = useNearby();
  const live = prefs.enabled;
  const [online, setOnline] = useState(null);
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
      </nav>
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
      <div className="pill" title="Backend status">
        <span className={`dot ${online === null ? "" : online ? "live" : "down"}`} />
        {online === null ? "Checking…" : online ? "Agents online" : "Backend unreachable"}
      </div>
    </header>
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
            <Route path="/stays" element={<Stays />} />
            <Route path="/explore" element={<Explore />} />
            <Route path="/nearby" element={<Nearby />} />
            <Route path="/deals" element={<Deals />} />
            <Route path="/tonight" element={<Tonight />} />
            <Route path="/people" element={<People />} />
            <Route path="/partners" element={<Partners />} />
            <Route path="/admin" element={<Admin />} />
            <Route path="/credits" element={<Credits />} />
            <Route path="*" element={<Home />} />
          </Routes>
        </motion.main>
      </AnimatePresence>
      <Toasts />
      <Footer />
    </div>
  );
}
