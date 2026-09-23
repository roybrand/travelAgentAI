/** Real Web Push: subscribe this browser to a Wayfinder People account, so it can be notified (new
 * messages, connection requests) even while the app is fully closed. Falls back gracefully wherever the
 * Push API is unsupported (Safari on older iOS, some in-app browsers). */

function urlBase64ToUint8Array(base64url) {
  const padded = base64url + "=".repeat((4 - (base64url.length % 4)) % 4);
  const raw = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

export function pushSupported() {
  return typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window;
}

/** The current subscription for this browser, if any (does not create one). */
export async function currentSubscription() {
  if (!pushSupported()) return null;
  try {
    const reg = await navigator.serviceWorker.ready;
    return await reg.pushManager.getSubscription();
  } catch {
    return null;
  }
}

/** Ask for notification permission, subscribe via the service worker, and tell the server. Returns the
 * subscription, or throws with a message fit to show the person. */
export async function subscribeThisDevice(publicKey, onSubscribed) {
  if (!pushSupported()) throw new Error("This browser does not support push notifications.");
  const perm = Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
  if (perm !== "granted") throw new Error("Notifications were not allowed. Enable them in your browser settings to turn this on.");
  const reg = await navigator.serviceWorker.ready;
  let sub = await reg.pushManager.getSubscription();
  if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(publicKey) });
  const json = sub.toJSON();
  await onSubscribed({ endpoint: json.endpoint, p256dh: json.keys.p256dh, auth: json.keys.auth });
  return sub;
}

/** Unsubscribe this browser and tell the server, best-effort either way. */
export async function unsubscribeThisDevice(onUnsubscribed) {
  const sub = await currentSubscription();
  if (!sub) return;
  const endpoint = sub.endpoint;
  try {
    await sub.unsubscribe();
  } catch {
    /* still tell the server so it stops trying */
  }
  await onUnsubscribed(endpoint).catch(() => {});
}
