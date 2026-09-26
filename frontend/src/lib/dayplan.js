export const PARTS = ["morning", "afternoon", "evening", "night"];
export const PART_LABEL = { morning: "Morning", afternoon: "Afternoon", evening: "Evening", night: "Night" };
export const PART_ICON = { morning: "🌅", afternoon: "☀️", evening: "🌆", night: "🌙" };

const NIGHT_TAGS = ["nightlife", "rooftop-bar", "pub", "nightclub", "bar"];
const MORNING_TAGS = ["museum", "gallery", "art", "historic", "old-town", "sightseeing", "viewpoint", "park", "quiet", "attraction"];
const AFTERNOON_TAGS = ["market", "shopping", "beachfront", "beach", "spa", "cafe", "restaurant"];

/** A reasonable time of day for an item, guessed from its tags and type. The traveler can move it afterwards. */
export function guessPart(item) {
  const tags = [...(item.tags || []), item.type].filter(Boolean);
  if (tags.some((t) => NIGHT_TAGS.includes(t))) return "night";
  if (tags.some((t) => MORNING_TAGS.includes(t))) return "morning";
  if (tags.some((t) => AFTERNOON_TAGS.includes(t))) return "afternoon";
  return "afternoon";
}

/** Everything a traveler could add to their plan: sights, adventures, and the real places they asked to see. */
export function candidateItems(guide) {
  if (!guide) return [];
  const withKey = (item, source) => {
    return { ...item, fixed_day: item.day || null, key: `${source}:${item.destination || ""}:${item.name}`, source, why: item.city && item.why ? `${item.city} · ${item.why}` : item.why || item.city || "" };
  };
  const places = (guide.places || []).map((p) => withKey(p, "sight"));
  const adventures = (guide.adventures || []).map((a) => withKey(a, "adventure"));
  const routes = (guide.route_ideas || []).map((p) => withKey({ ...p, why: p.area ? `${p.area} · ${p.why || "Along your route"}` : p.why }, "route"));
  const typed = Object.entries(guide.by_type || {}).flatMap(([type, group]) =>
    (group.places || []).map((p) => withKey({ ...p, type, typeLabel: group.label, why: p.opening_hours ? `${group.label} · open ${p.opening_hours}` : group.label }, "place")),
  );
  const seen = new Set();
  return [...places, ...adventures, ...routes, ...typed].filter((i) => {
    if (seen.has(i.key)) return false;
    seen.add(i.key);
    return true;
  });
}

/** Where a newly-added item lands. On the Day plan tab the traveler picks it (the open day and the chosen time of
 * day), so it goes exactly there. Otherwise fall back to the day with the fewest items so far and a guessed time. */
export function nextSlot(schedule, nights, item, target) {
  if (target?.day) {
    const day = Math.min(Math.max(1, target.day), Math.max(1, nights));
    return { day, part: PARTS.includes(target.part) ? target.part : guessPart(item) };
  }
  const counts = Array.from({ length: Math.max(1, nights) }, () => 0);
  Object.values(schedule).forEach((s) => {
    if (s.day >= 1 && s.day <= counts.length) counts[s.day - 1] += 1;
  });
  let day = 1;
  let min = Infinity;
  counts.forEach((n, i) => {
    if (n < min) {
      min = n;
      day = i + 1;
    }
  });
  return { day, part: guessPart(item) };
}

/** The candidates already on the plan, in day and time-of-day order, each carrying its schedule slot. */
export function scheduledItems(candidates, schedule) {
  const byKey = new Map(candidates.map((i) => [i.key, i]));
  return Object.entries(schedule)
    .map(([key, slot]) => {
      const item = byKey.get(key) || slot.item;
      return item ? { ...item, ...slot, item: undefined } : null;
    })
    .filter(Boolean)
    .sort((a, b) => a.day - b.day || PARTS.indexOf(a.part) - PARTS.indexOf(b.part) || a.order - b.order);
}

/** A typical start time for each time of day, used for calendar entries. */
export const PART_TIME = { morning: "09:30", afternoon: "14:00", evening: "19:00", night: "22:00" };
