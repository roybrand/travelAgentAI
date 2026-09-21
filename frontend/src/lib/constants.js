// Popular shortcuts on the home page. These four also have hand-curated highlights, costs and photos.
export const SHOWCASE = [
  { code: "NAP", city: "Naples & Amalfi", country: "Italy", tagline: "Cliffside villages, volcano views, the birthplace of pizza", photo: "NAP-amalfi", alt: ["NAP-capri", "NAP-vesuvius"] },
  { code: "LIS", city: "Lisbon & Sintra", country: "Portugal", tagline: "Golden trams, fairy-tale palaces, Atlantic waves", photo: "LIS-hero", alt: ["LIS-sintra", "LIS-tram"] },
  { code: "TYO", city: "Tokyo", country: "Japan", tagline: "Neon crossings, ancient shrines, Mount Fuji on the horizon", photo: "TYO-hero", alt: ["TYO-shibuya", "TYO-fuji"] },
  { code: "DXB", city: "Dubai & Abu Dhabi", country: "UAE", tagline: "Record-breaking skylines and endless desert", photo: "DXB-hero", alt: ["DXB-burj", "DXB-safari"] },
];

// Interests the live data can actually evaluate (from OpenStreetMap signals and Wikipedia)
export const INTERESTS = [
  ["beachfront", "Beachfront"],
  ["nightlife", "Nightlife"],
  ["food-scene", "Food scene"],
  ["old-town", "Old town"],
  ["spa", "Spa"],
  ["quiet", "Quiet"],
  ["pet-friendly", "Pet friendly"],
];

// Older curated tags from the demo content, still shown nicely if they appear
const EXTRA_TAG_LABELS = {
  "michelin-nearby": "Fine dining",
  "rooftop-bar": "Rooftop bars",
  "family-friendly": "Family",
  "supercar-rental-nearby": "Supercars",
};

export const TAG_LABEL = { ...EXTRA_TAG_LABELS, ...Object.fromEntries(INTERESTS) };

export const KIND_META = {
  restaurant: { label: "Dining", color: "#f59e0b" },
  tour: { label: "Tour", color: "#818cf8" },
  experience: { label: "Experience", color: "#f472b6" },
  spa: { label: "Spa", color: "#34d399" },
};

// How each data source is labelled in the UI
export const SOURCE_MODE = {
  live: { label: "Live", tone: "ok" },
  amadeus: { label: "Live offers", tone: "ok" },
  estimate: { label: "Estimate", tone: "warn" },
  demo: { label: "Demo", tone: "muted" },
  none: { label: "Unavailable", tone: "muted" },
};
