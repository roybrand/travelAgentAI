/* Wayfinder service worker.
 * It does three things only: it lets the app be installed, it lets phones show the "nearby" notifications
 * (mobile browsers only allow notifications from a service worker), and it shows real push notifications
 * sent from the server (new messages, connection requests) even while Wayfinder is fully closed. It does
 * not cache pages, and a push payload is only ever a title, a short body and a destination URL. */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    /* an empty or unreadable push shows a generic notification below */
  }
  const title = data.title || "Wayfinder";
  event.waitUntil(
    self.registration.showNotification(title, { body: data.body || "", data: { url: data.url || "/people" }, icon: "/icon-192.png" }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/nearby";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const w of windows) {
        if ("focus" in w) {
          if ("navigate" in w) w.navigate(url);
          return w.focus();
        }
      }
      return self.clients.openWindow(url);
    }),
  );
});
