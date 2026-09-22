export const PARTS = ["morning", "afternoon", "evening", "night"];
export const PART_LABEL = { morning: "Morning", afternoon: "Afternoon", evening: "Evening", night: "Night" };
export const PART_ICON = { morning: "🌅", afternoon: "☀️", evening: "🌆", night: "🌙" };

const NIGHT_TAGS = ["nightlife", "rooftop-bar", "pub", "nightclub", "bar"];
const MORNING_TAGS = ["museum", "gallery", "art", "historic", "old-town", "sightseeing", "viewpoint", "park", "quiet", "attraction"];
const AFTERNOON_TAGS = ["market", "shopping", "beachfront", "beach", "spa", "cafe", "restaurant"];

/** A reasonable time of day for an item, guessed from its tags and type. The traveler can move it afterwards. */
export function guessPart(item) {
  const tags = [...(item.tags || []), item.type].filter(Boolean);
  if (tags.some((t) => NIGHT_TAGS.includes(t))) return "evening";
  if (tags.some((t) => MORNING_TAGS.includes(t))) return "morning";
  if (tags.some((t) => AFTERNOON_TAGS.includes(t))) return "afternoon";
  return "afternoon";
}

/** Everything a traveler could add to their plan: sights, adventures, and the real places they asked to see. */
export function candidateItems(guide) {
  if (!guide) return [];
  const places = (guide.places || []).map((p) => ({ ...p, key: p.name, source: "sight" }));
  const adventures = (guide.adventures || []).map((a) => ({ ...a, key: a.name, source: "adventure" }));
  const typed = Object.entries(guide.by_type || {}).flatMap(([type, group]) =>
    (group.places || []).map((p) => ({ ...p, key: p.name, source: "place", type, typeLabel: group.label, why: p.opening_hours ? `${group.label} · open ${p.opening_hours}` : group.label })),
  );
  const seen = new Set();
  return [...places, ...adventures, ...typed].filter((i) => {
    if (seen.has(i.key)) return false;
    seen.add(i.key);
    return true;
  });
}

/** Where a newly-added item lands: the day with the fewest items so far, spreading the plan out evenly. */
export function nextSlot(schedule, nights, item) {
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
  return candidates
    .filter((i) => schedule[i.key])
    .map((i) => ({ ...i, ...schedule[i.key] }))
    .sort((a, b) => a.day - b.day || PARTS.indexOf(a.part) - PARTS.indexOf(b.part) || a.order - b.order);
}
