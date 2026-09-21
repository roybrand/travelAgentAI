export const SHOWCASE = [
  { code: "NAP", city: "Naples & Amalfi", country: "Italy", tagline: "Cliffside villages, volcano views, the birthplace of pizza", photo: "NAP-amalfi", alt: ["NAP-capri", "NAP-vesuvius"] },
  { code: "LIS", city: "Lisbon & Sintra", country: "Portugal", tagline: "Golden trams, fairy-tale palaces, Atlantic waves", photo: "LIS-hero", alt: ["LIS-sintra", "LIS-tram"] },
  { code: "TYO", city: "Tokyo", country: "Japan", tagline: "Neon crossings, ancient shrines, Mount Fuji on the horizon", photo: "TYO-hero", alt: ["TYO-shibuya", "TYO-fuji"] },
  { code: "DXB", city: "Dubai & Abu Dhabi", country: "UAE", tagline: "Record-breaking skylines and endless desert", photo: "DXB-hero", alt: ["DXB-burj", "DXB-safari"] },
];

export const INTERESTS = [
  ["beachfront", "Beachfront"], ["nightlife", "Nightlife"], ["michelin-nearby", "Fine dining"],
  ["spa", "Spa"], ["old-town", "Old town"], ["rooftop-bar", "Rooftop bars"],
  ["family-friendly", "Family"], ["quiet", "Quiet"], ["pet-friendly", "Pet friendly"],
  ["supercar-rental-nearby", "Supercars"],
];

export const TAG_LABEL = Object.fromEntries(INTERESTS);

export const CITY_NAME = Object.fromEntries(SHOWCASE.map((s) => [s.code, s.city]));

export const KIND_META = {
  restaurant: { label: "Dining", color: "#f59e0b" },
  tour: { label: "Tour", color: "#818cf8" },
  experience: { label: "Experience", color: "#f472b6" },
  spa: { label: "Spa", color: "#34d399" },
};
