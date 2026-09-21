const STAY_KEYS = ["stay-1", "stay-2", "stay-3", "stay-4", "stay-5", "stay-6"];

const hash = (s = "") => [...s].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7);

/** Real hotels have no photos in free data, so show generic illustrations (labelled as such). */
export function stayPhotos(hotel) {
  if (hotel.photos?.length) return hotel.photos;
  const start = hash(hotel.id || hotel.name) % STAY_KEYS.length;
  return [0, 1, 2].map((i) => STAY_KEYS[(start + i) % STAY_KEYS.length]);
}

/** Star class or guest rating, whichever the data source provides. */
export function qualityLabel(h) {
  if (h.rating != null) return `${Number(h.rating).toFixed(1)}★`;
  if (h.stars) return `${h.stars}-star`;
  return null;
}

/** Numeric quality for sorting (guest rating if present, else stars, else unknown). */
export function qualityValue(h) {
  return h.rating ?? h.stars ?? 0;
}

export const PRICE_SOURCE = {
  amadeus: { label: "Live price", tone: "ok" },
  estimate: { label: "Estimated price", tone: "warn" },
  demo: { label: "Demo price", tone: "muted" },
};
