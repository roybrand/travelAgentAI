const PUSH_KEY = "wf.nearby.push.v1";
const DAILY_PUSH_CAP = 3; // device notifications per day, shared by every kind of alert
const QUIET_FROM = 22; // no device notifications from 10 pm...
const QUIET_TO = 8; // ...until 8 am, unless the user turns quiet hours off

/** Device notifications are rationed: a daily cap and (optional) quiet hours. In-app pop-ups are not limited. */
export function mayNotify(quiet = true) {
  const now = new Date();
  const h = now.getHours();
  if (quiet && (h >= QUIET_FROM || h < QUIET_TO)) return false;
  const day = now.toLocaleDateString("en-CA");
  let used = { day, n: 0 };
  try {
    const s = JSON.parse(localStorage.getItem(PUSH_KEY) || "null");
    if (s?.day === day) used = s;
  } catch {
    /* storage may be unavailable */
  }
  if (used.n >= DAILY_PUSH_CAP) return false;
  try {
    localStorage.setItem(PUSH_KEY, JSON.stringify({ day, n: used.n + 1 }));
  } catch {
    /* ignore */
  }
  return true;
}

/** Prefer the service worker (works on phones); fall back to the page Notification API. */
export async function showDeviceNotification(rec, url = "/nearby") {
  const options = { body: rec.reason, tag: rec.id, data: { url }, icon: "/icon-192.png" };
  try {
    const reg = await navigator.serviceWorker?.getRegistration();
    if (reg?.showNotification) return void (await reg.showNotification(rec.title, options));
  } catch {
    /* fall through */
  }
  try {
    new Notification(rec.title, options);
  } catch {
    /* some browsers only allow notifications from a service worker */
  }
}
