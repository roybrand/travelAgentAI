/** Where the traveler is in their trip, what comes next, and what is worth doing or knowing today. Pure functions,
 * so the trip page, the care card and the timeline agree on the same facts. */
import { PARTS, PART_LABEL, PART_TIME, guessPart } from "./dayplan";
import { distanceM } from "./format";

export const ROUTE_RADIUS_M = 1200; // "on your way": a partner deal within an easy walk of one of that day's stops
export const CENTRE_RADIUS_M = 3000; // when nothing that day has a known position, "near the centre" is the honest fallback

const localIso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/** The calendar date of trip day `n` (day 1 is the start date). */
export function dayDate(startIso, n) {
  const d = new Date(startIso + "T00:00:00");
  d.setDate(d.getDate() + n - 1);
  return localIso(d);
}

/** The time of day now, on the same four parts the plan uses. */
export function partNow(now = new Date()) {
  const h = now.getHours();
  if (h < 5) return "night";
  if (h < 12) return "morning";
  if (h < 17) return "afternoon";
  if (h < 21) return "evening";
  return "night";
}

/** before / during / after the trip, with today's trip day while it's on. The trip has nights + 1 days: the last
 * one is the day you fly home. */
export function tripPhase(req, nights, now = new Date()) {
  const today = localIso(now);
  const lastDay = dayDate(req.start_date, nights + 1);
  if (today < req.start_date) {
    const days = Math.round((new Date(req.start_date + "T00:00:00") - new Date(today + "T00:00:00")) / 86400000);
    return { phase: "before", daysToGo: days, today };
  }
  if (today > lastDay) return { phase: "after", today };
  const day = Math.round((new Date(today + "T00:00:00") - new Date(req.start_date + "T00:00:00")) / 86400000) + 1;
  return { phase: "during", day, part: partNow(now), today };
}

/** Today's next planned item from the current time of day on (a morning item is "next" until the afternoon). */
export function nextUp(items, day, part) {
  const from = PARTS.indexOf(part);
  return items.filter((i) => i.day === day && PARTS.indexOf(i.part) >= from)[0] || null;
}

export const directionsUrl = (p) => `https://www.google.com/maps/dir/?api=1&destination=${p.lat},${p.lng}`;

/** Where a day's stops are: its planned items with a position, else the stay, else the city centre (with a wider
 * radius, and named as the centre so the deal says honestly what it is near). */
export function dayStops(items, day, hotel, centre) {
  const stops = items.filter((i) => i.day === day && i.lat != null);
  if (stops.length) return stops;
  if (hotel?.lat != null) return [{ name: hotel.name, lat: hotel.lat, lng: hotel.lng }];
  return centre?.lat != null ? [{ name: "the city centre", lat: centre.lat, lng: centre.lng, radius: CENTRE_RADIUS_M }] : [];
}

/** Partner deals along each day's route: valid on that date and within ROUTE_RADIUS_M of one of that day's stops.
 * The server's order is kept (match, real discount, distance -- never payment); distance only breaks ties. Each deal
 * appears on one day only, the first it fits, except that `pinDay` (today, during the trip) always gets its own. */
export function routeDeals(deals, { days, startIso, items, hotel, centre, pinDay = null, perDay = 2 }) {
  const out = {};
  const used = new Set();
  const order = [...days].sort((a, b) => (a === pinDay ? -1 : b === pinDay ? 1 : a - b));
  order.forEach((d) => {
    const date = dayDate(startIso, d);
    const stops = dayStops(items, d, hotel, centre);
    out[d] = deals
      .map((deal, rank) => {
        if (deal.lat == null || (deal.valid_from && deal.valid_from > date) || (deal.valid_to && deal.valid_to < date)) return null;
        let best = null;
        stops.forEach((s) => {
          const m = distanceM(s, deal);
          if (m <= (s.radius || ROUTE_RADIUS_M) && (!best || m < best.m)) best = { m, near: s.name };
        });
        return best && { ...deal, rank, distance_m: Math.round(best.m), near: best.near };
      })
      .filter((x) => x && (d === pinDay || !used.has(x.id)))
      .sort((a, b) => a.rank - b.rank || a.distance_m - b.distance_m)
      .slice(0, perDay);
    out[d].forEach((x) => used.add(x.id));
  });
  return out;
}

/** One idea for an empty slot: the best fit for that time of day that isn't planned or already suggested. */
export function slotSuggestion(candidates, scheduled, taken, part, hotel) {
  const score = (i) => (guessPart(i) === part ? 2 : 0) + (i.matches?.length ? 1 : 0);
  const pick = candidates
    .filter((c) => !scheduled.has(c.key) && !taken.has(c.key))
    .sort((a, b) => score(b) - score(a))[0];
  if (!pick || score(pick) < 2) return null;
  taken.add(pick.key);
  const away = hotel?.lat != null && pick.lat != null ? Math.round(distanceM(hotel, pick)) : null;
  return { item: pick, away };
}

/** The short to-do list that makes the plan feel looked after, most useful first. Each task can carry an action. */
export function careTasks({ phase, nights, items, booking, bookingChanged, flight, hotel }) {
  if (phase.phase !== "before") return [];
  const tasks = [];
  const live = booking && booking.status !== "cancelled";
  if (live && bookingChanged) tasks.push({ key: "rebook", icon: "⚠️", text: "Your plan changed after you booked", action: { kind: "book", label: "Review" } });
  if (!live) tasks.push({ key: "book", icon: "🎫", text: "Flights and stay aren't booked yet", action: { kind: "book", label: "Book" } });
  const empty = Array.from({ length: nights }, (_, i) => i + 1).filter((d) => !items.some((i) => i.day === d));
  empty.slice(0, 2).forEach((d) => tasks.push({ key: `empty-${d}`, icon: "🗓️", text: `Day ${d} has nothing planned yet`, action: { kind: "day", day: d, label: "Fill it" } }));
  if (empty.length > 2) tasks.push({ key: "empty-more", icon: "🗓️", text: `${empty.length - 2} more days are still open`, action: { kind: "day", day: empty[2], label: "Show" } });
  if (!live && (flight.price_source === "estimate" || hotel.price_source === "estimate")) {
    tasks.push({ key: "estimate", icon: "ℹ️", text: "Some prices are estimates, not quotes. They're labelled Estimate" });
  }
  if (live && !bookingChanged) tasks.push({ key: "calendar", icon: "📅", text: "Put the trip in your calendar", action: { kind: "book", label: "Calendar" } });
  return tasks;
}

export const partStarts = (part) => `${PART_LABEL[part].toLowerCase()}, from ${PART_TIME[part]}`;
