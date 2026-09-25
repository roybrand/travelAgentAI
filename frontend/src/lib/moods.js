/** Moods a traveler can set for a day, and what each one leans towards. A mood only re-orders that day's ideas,
 * deals along the route and pop-ups; it never changes the trip's own interests. Matching reads an idea's tags,
 * its kind of place and its name and description, because the tags alone are coarse. */
// Whole words (with an optional plural), so "park" never matches "Parkhotel" nor "bar" match "Barceloneta".
const words = (list) => new RegExp(`\\b(?:${list})(?:s|es)?\\b`, "i");

export const MOODS = [
  { key: "adventurous", icon: "🧗", label: "Adventurous", interests: ["beachfront"], place_types: ["park", "viewpoint", "beach"], sources: ["adventure"],
    rx: words("hike|hiking|trail|surf|surfing|kayak|sail|sailing|boat|bike|climb|mountain|island|waterfall|adventure|day trip|coast|cliff") },
  { key: "chill", icon: "😌", label: "Chill", interests: ["quiet", "spa", "beachfront"], place_types: ["park", "beach", "cafe", "spa"],
    rx: words("park|garden|beach|spa|bath|cafe|viewpoint|sunset|lake|quiet|terrace") },
  { key: "romantic", icon: "💞", label: "Romantic", interests: ["food-scene"], place_types: ["viewpoint", "restaurant"],
    rx: words("sunset|viewpoint|miradouro|rooftop|wine|dinner|sail|sailing|cruise|garden|palace|candlelit") },
  { key: "social", icon: "🎉", label: "Social", interests: ["nightlife"], place_types: ["pub", "nightclub"],
    rx: words("bar|pub|club|nightlife|party|parties|tapas|crawl|live music|market") },
  { key: "foodie", icon: "🍽️", label: "Foodie", interests: ["food-scene"], place_types: ["restaurant", "market", "cafe"],
    rx: words("food|market|tapas|tasting|restaurant|cafe|wine|cooking|brunch|dinner|bakery|small plates") },
  { key: "cultural", icon: "🏛️", label: "Cultural", interests: ["old-town"], place_types: ["museum", "gallery", "historic", "theatre"],
    rx: words("museum|gallery|galleries|cathedral|church|basilica|palace|castle|historic|old town|quarter|theatre|theater|opera|monastery|sagrada") },
  { key: "easy", icon: "😴", label: "Taking it easy", interests: ["quiet", "spa"], place_types: ["cafe", "spa", "park"],
    rx: words("cafe|spa|bath|park|garden|viewpoint|terrace"), avoid: words("hike|hiking|trail|day trip|surf|climb|club|crawl") },
];
export const MOOD = Object.fromEntries(MOODS.map((m) => [m.key, m]));

// Which moods each kind of partner deal suits.
const DEAL_MOODS = {
  restaurant: ["foodie", "romantic"], bar: ["social", "romantic"], party: ["social"], spa: ["chill", "easy", "romantic"],
  tour: ["cultural", "adventurous"], activity: ["adventurous", "social"], hotel: ["chill"], car_rental: ["adventurous"],
};

const text = (i) => [i.name, i.title, i.why, i.description, i.type, ...(i.tags || []), ...(i.matches || [])].filter(Boolean).join(" ");

/** How well an idea suits a mood: 0 (no) to about 3 (clearly). Negative when the mood avoids it. */
export function moodScore(item, key) {
  const m = MOOD[key];
  if (!m) return 0;
  const t = text(item);
  let s = 0;
  if (m.rx.test(t)) s += 2;
  if ((item.tags || []).some((x) => m.interests.includes(x)) || m.place_types.includes(item.type)) s += 1;
  if (m.sources?.includes(item.source)) s += 1;
  if (m.avoid?.test(t)) s -= 3;
  return s;
}

export function dealMoodScore(deal, key) {
  if (!MOOD[key]) return 0;
  return (DEAL_MOODS[deal.category]?.includes(key) ? 2 : 0) + (MOOD[key].rx.test(text(deal)) ? 1 : 0);
}

// Whole words only: "bar" must not match Barceloneta, nor "park" match Parkhotel.
const OUTDOOR = /\b(parks?|gardens?|beach(es)?|coast(al)?|coves?|hikes?|hiking|trails?|viewpoints?|miradouros?|sunset|sail(ing)?|boats?|cruises?|kayak(ing)?|surf(ing)?|islands?|lakes?|waterfalls?|nature|mountains?|montserrat|outdoors?|zoo|walks?|walking|lanes|promenade|seafront|neighbou?rhood|squares?|bike|cycling|cliffs?|day trip)\b/i;
const INDOOR = /\b(museums?|galler(y|ies)|cathedral|churches|church|basilica|palace|theat(re|er)s?|opera|spas?|baths?|cafes?|restaurants?|tasting|cooking|aquarium|library|shopping|clubs?|bars?|pubs?|cinema|market hall|monastery|tapas|wine)\b/i;

/** Rough indoor / outdoor reading of an idea, for rainy days. Unknown stays unknown (neither). */
export const isOutdoor = (i) => ["beach", "park", "viewpoint"].includes(i.type) || (OUTDOOR.test(text(i)) && !INDOOR.test(i.name || ""));
export const isIndoor = (i) => ["museum", "gallery", "theatre", "cafe", "restaurant", "spa", "pub", "nightclub"].includes(i.type) || (INDOOR.test(text(i)) && !isOutdoor(i));

/** The extra score a rainy (wet) day gives an idea: indoors up, outdoors down. */
export const weatherScore = (i, wet) => (!wet ? 0 : isIndoor(i) ? 2 : isOutdoor(i) ? -3 : 0);
