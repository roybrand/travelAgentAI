const KEY = "wf.profile.v1";

/** The traveler profile lives only in this browser (localStorage) unless they clear it. */
export function loadProfile() {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "null");
  } catch {
    return null;
  }
}
export function storeProfile(p) {
  try {
    localStorage.setItem(KEY, JSON.stringify(p));
  } catch {
    /* storage may be unavailable */
  }
}
export function clearStoredProfile() {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}

/** Shrink a chosen photo to a small JPEG data URL (max 768 px) before it is sent anywhere. */
export function resizeImage(file, max = 768) {
  return new Promise((resolve, reject) => {
    if (!file.type.startsWith("image/")) return reject(new Error("Please choose an image file."));
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      const scale = Math.min(1, max / Math.max(img.width, img.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      resolve(canvas.toDataURL("image/jpeg", 0.82));
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("That image could not be read."));
    };
    img.src = url;
  });
}

export const PLACE_TYPE_LABEL = {
  museum: "Museums", gallery: "Art galleries", pub: "Pubs and bars", nightclub: "Nightclubs", park: "Parks and gardens",
  viewpoint: "Viewpoints", market: "Markets", historic: "Historic sites", theatre: "Theatres and venues", beach: "Beaches",
  cafe: "Cafes", restaurant: "Restaurants", spa: "Spas", attraction: "Family attractions",
};
