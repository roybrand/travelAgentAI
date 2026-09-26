import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

// Standard OpenStreetMap tiles need no API key; the dark look comes from a CSS filter (see styles.css).
const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

function pinElement(pin, selected) {
  const el = document.createElement("div");
  el.className = `pin pin-${pin.kind}${selected ? " sel" : ""}`;
  el.style.setProperty("--c", pin.color || "#2dd4bf");
  const span = document.createElement("span");
  span.textContent = pin.label ?? "";
  el.appendChild(span);
  return el;
}

/**
 * pins: [{ id, lat, lng, kind: "hotel" | "sight" | "venue", label, title, color }]
 * Map tiles need internet; offline the pins still render over a dark background.
 */
export default function MapView({ center, pins, path = [], paths = null, selectedId, highlightId, onSelect, height = 440 }) {
  const box = useRef(null);
  const map = useRef(null);
  const layer = useRef(null);
  const markers = useRef(new Map());
  const fit = useRef(() => {});
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const selectedRef = useRef(selectedId);
  selectedRef.current = selectedId;

  useEffect(() => {
    map.current = L.map(box.current, { scrollWheelZoom: false }).setView(center, 12);
    L.tileLayer(TILES, { attribution: ATTR, maxZoom: 19 }).addTo(map.current);
    layer.current = L.layerGroup().addTo(map.current);
    // Page transitions and charts settle the layout after mount, so re-measure and re-fit during the first moments.
    const born = performance.now();
    const ro = new ResizeObserver(() => {
      if (!map.current) return;
      map.current.invalidateSize();
      if (performance.now() - born < 3000) fit.current();
    });
    ro.observe(box.current);
    return () => {
      ro.disconnect();
      map.current.remove();
      map.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!map.current) return;
    layer.current.clearLayers();
    markers.current.clear();
    const pts = [];
    const routePaths = paths || (path?.length ? [{ points: path }] : []);
    const pathPts = [];
    routePaths.forEach((routePath) => {
      const points = (routePath.points || routePath || []).filter((p) => p?.lat != null && p?.lng != null).map((p) => [p.lat, p.lng]);
      if (points.length > 1) {
        L.polyline(points, {
          color: routePath.color || "#f5c76a",
          weight: routePath.weight || 4,
          opacity: routePath.opacity ?? 0.9,
          dashArray: routePath.dashArray ?? "8 8",
        }).addTo(layer.current);
        pathPts.push(...points);
      }
    });
    pts.push(...pathPts);
    pins.forEach((pin) => {
      const small = pin.kind === "venue";
      const offset = pin.zIndexOffset ?? (small ? 0 : pin.kind === "hotel" ? 300 : 500);
      const markerLat = pin.displayLat ?? pin.lat;
      const markerLng = pin.displayLng ?? pin.lng;
      if (pin.displayLat != null && pin.displayLng != null && (pin.displayLat !== pin.lat || pin.displayLng !== pin.lng)) {
        L.polyline([[pin.lat, pin.lng], [pin.displayLat, pin.displayLng]], { color: pin.color || "#ffffff", weight: 1.5, opacity: 0.65 }).addTo(layer.current);
      }
      const icon = L.divIcon({
        html: pinElement(pin, pin.id === selectedRef.current),
        className: "pin-wrap",
        iconSize: small ? [16, 16] : pin.kind === "hotel" ? [64, 30] : pin.kind === "you" ? [22, 22] : [34, 34],
        iconAnchor: small ? [8, 8] : pin.kind === "hotel" ? [32, 15] : pin.kind === "you" ? [11, 11] : [17, 17],
      });
      const m = L.marker([markerLat, markerLng], { icon, title: pin.title, zIndexOffset: offset });
      if (pin.title) m.bindTooltip(pin.title, { direction: "top", offset: [0, -10], opacity: 0.95 });
      m.on("click", () => {
        if (pin.title) m.openTooltip();
        if (onSelectRef.current) onSelectRef.current(pin.id);
      });
      m.addTo(layer.current);
      markers.current.set(pin.id, m);
      pts.push([markerLat, markerLng], [pin.lat, pin.lng]);
    });
    fit.current = () => {
      if (!map.current) return;
      if (pts.length > 1) map.current.fitBounds(pts, { padding: pathPts.length > 1 ? [34, 34] : [46, 46], maxZoom: pathPts.length > 1 ? 10 : 14, animate: false });
      else if (pts.length === 1) map.current.setView(pts[0], 13, { animate: false });
    };
    fit.current();
  }, [pins, path, paths]);

  // Highlight follows hover or selection; the map only flies when the selection itself changes,
  // and not on first render (so the initial view keeps every pin in frame).
  const mounted = useRef(false);
  useEffect(() => {
    markers.current.forEach((m, id) => {
      const el = m.getElement()?.firstChild;
      if (el) el.classList.toggle("sel", id === (highlightId || selectedId));
    });
  }, [selectedId, highlightId, pins]);

  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    const m = selectedId && markers.current.get(selectedId);
    if (m && map.current) map.current.flyTo(m.getLatLng(), Math.max(map.current.getZoom(), 13), { duration: 0.7 });
  }, [selectedId]);

  return <div ref={box} className="map" style={{ height }} role="application" aria-label="Map" />;
}
