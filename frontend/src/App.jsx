import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { checkHealth } from "./api";
import { useTrip } from "./state/TripContext.jsx";
import Home from "./pages/Home.jsx";
import Trip from "./pages/Trip.jsx";
import Stays from "./pages/Stays.jsx";
import Explore from "./pages/Explore.jsx";
import Credits from "./pages/Credits.jsx";

function Header() {
  const { trip } = useTrip();
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
      {trip && (
        <nav className="tabs" aria-label="Trip sections">
          <NavLink to="/trip">Your trip</NavLink>
          <NavLink to="/stays">Stays</NavLink>
          <NavLink to="/explore">Explore</NavLink>
        </nav>
      )}
      <div className="pill" title="Backend status">
        <span className={`dot ${online === null ? "" : online ? "live" : "down"}`} />
        {online === null ? "Checking…" : online ? "Agents online" : "Backend unreachable"}
      </div>
    </header>
  );
}

function Footer() {
  return (
    <footer className="footer">
      <div>
        <b>Wayfinder AI</b> · LangGraph orchestration · MCP tool servers · FastAPI · React
      </div>
      <div className="footer-note">
        Prototype. Flight and stay inventory, prices, discounts and price history are simulated demo data.
        Destination photos are openly licensed (<Link to="/credits">see credits</Link>).
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
            <Route path="/credits" element={<Credits />} />
            <Route path="*" element={<Home />} />
          </Routes>
        </motion.main>
      </AnimatePresence>
      <Footer />
    </div>
  );
}
