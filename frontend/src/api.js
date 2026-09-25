async function readError(res) {
  let detail = `Request failed (${res.status})`;
  try {
    const j = await res.json();
    if (Array.isArray(j.detail)) detail = j.detail.map((d) => String(d.msg).replace(/^Value error, /, "")).join("; ");
    else if (j.detail) detail = j.detail;
  } catch {
    /* keep the generic message */
  }
  return new Error(detail);
}

export async function planTrip(payload) {
  const res = await fetch("/api/plan-trip", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw await readError(res);
  return res.json();
}

export async function parseRequest(text) {
  const res = await fetch("/api/parse-request", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw await readError(res);
  return res.json();
}

export async function fetchConfig() {
  try {
    const r = await fetch("/api/config");
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}

export async function fetchDestinations() {
  try {
    const r = await fetch("/api/destinations");
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}

export async function checkHealth(attempts = 3) {
  for (let i = 0; i < attempts; i++) {
    try {
      const r = await fetch("/health");
      if (r.ok) return true;
    } catch {
      /* retry */
    }
    await new Promise((res) => setTimeout(res, 800));
  }
  return false;
}

export async function fetchNearby(payload) {
  const res = await fetch("/api/nearby", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw await readError(res);
  return res.json();
}

export async function buildTrip(text, image) {
  const res = await fetch("/api/build-trip", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, image: image || null }),
  });
  if (!res.ok) throw await readError(res);
  return res.json();
}

// ---------------------------------------------------------------- deals, events, partner portal, moderation

/** One JSON request. `token` is a partner session, `admin` the moderation token. Throws with the server's message. */
export async function request(path, { method = "GET", body, token, admin } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  if (admin) headers["X-Admin-Token"] = admin;
  const res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!res.ok) {
    const err = await readError(res);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

const qs = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== "")).toString();

export const fetchDeals = (params) => request(`/api/deals?${qs(params)}`);
export const fetchFeaturedDeals = (dest) => request(`/api/deals/featured?${qs({ dest })}`);
export const fetchDealOptions = () => request("/api/deals/options");
export const fetchEvents = (params) => request(`/api/events?${qs(params)}`);
export const trackDealClick = (id) => request(`/api/deals/${id}/click`, { method: "POST" }).catch(() => {});

export const partner = {
  register: (body) => request("/api/partners/register", { method: "POST", body }),
  login: (body) => request("/api/partners/login", { method: "POST", body }),
  logout: (token) => request("/api/partners/logout", { method: "POST", token }).catch(() => {}),
  me: (token) => request("/api/partners/me", { token }),
  create: (token, body) => request("/api/partners/deals", { method: "POST", token, body }),
  update: (token, id, body) => request(`/api/partners/deals/${id}`, { method: "PUT", token, body }),
  pause: (token, id, paused) => request(`/api/partners/deals/${id}/pause`, { method: "POST", token, body: { paused } }),
  end: (token, id) => request(`/api/partners/deals/${id}`, { method: "DELETE", token }),
  apiKey: (token) => request("/api/partners/api-key", { method: "POST", token }),
  geocode: (token, q, dest) => request(`/api/partners/geocode?${qs({ q, dest })}`, { token }),
  feature: (token, id, success_url, cancel_url) => request(`/api/partners/deals/${id}/feature`, { method: "POST", token, body: { success_url, cancel_url } }),
  changePassword: (token, current_password, new_password) => request("/api/partners/change-password", { method: "POST", token, body: { current_password, new_password } }),
};

export const admin = {
  analytics: (token, days = 30) => request(`/api/admin/analytics/summary?days=${days}`, { admin: token }),
  pending: (token) => request("/api/admin/deals", { admin: token }),
  approve: (token, id) => request(`/api/admin/deals/${id}/approve`, { method: "POST", admin: token }),
  reject: (token, id, reason) => request(`/api/admin/deals/${id}/reject`, { method: "POST", admin: token, body: { reason } }),
  partners: (token) => request("/api/admin/partners", { admin: token }),
  setStatus: (token, id, status) => request(`/api/admin/partners/${id}/status`, { method: "POST", admin: token, body: { status } }),
};

export const fetchTonight = (params) => request(`/api/tonight?${qs(params)}`);

// ---------------------------------------------------------------- People (accounts, places, finding people, chat)

export const people = {
  options: () => request("/api/people/options"),
  counts: (keys, day) => request(`/api/people/counts?${qs({ keys: keys.join(","), day })}`),
  register: (body) => request("/api/people/register", { method: "POST", body }),
  login: (body) => request("/api/people/login", { method: "POST", body }),
  logout: (token) => request("/api/people/logout", { method: "POST", token }).catch(() => {}),
  me: (token) => request("/api/people/me", { token }),
  get: (token, id) => request(`/api/people/${id}`, { token }),
  update: (token, body) => request("/api/people/me", { method: "PATCH", token, body }),
  photo: (token, image) => request("/api/people/me/photo", { method: "POST", token, body: { image } }),
  removePhoto: (token) => request("/api/people/me/photo", { method: "DELETE", token }),
  deleteMe: (token, password) => request("/api/people/me/delete", { method: "POST", token, body: { password } }),
  attend: (token, body) => request("/api/people/attend", { method: "POST", token, body }),
  unattend: (token, id) => request(`/api/people/attend/${id}`, { method: "DELETE", token }),
  attendees: (token, place_key, day) => request(`/api/people/attendees?${qs({ place_key, day })}`, { token }),
  looking: (token, body) => request("/api/people/looking", { method: "POST", token, body }),
  matches: (token, id) => request(`/api/people/looking/${id}/matches`, { token }),
  stopLooking: (token, id) => request(`/api/people/looking/${id}`, { method: "DELETE", token }),
  connect: (token, to_user, message) => request("/api/people/connect", { method: "POST", token, body: { to_user, message } }),
  connections: (token) => request("/api/people/connections", { token }),
  respond: (token, id, accept) => request(`/api/people/connections/${id}/respond`, { method: "POST", token, body: { accept } }),
  messages: (token, id, after = 0) => request(`/api/people/chats/${id}/messages?after=${after}`, { token }),
  send: (token, id, body) => request(`/api/people/chats/${id}/messages`, { method: "POST", token, body: { body } }),
  block: (token, user_id) => request("/api/people/block", { method: "POST", token, body: { user_id } }),
  unblock: (token, user_id) => request("/api/people/unblock", { method: "POST", token, body: { user_id } }),
  report: (token, body) => request("/api/people/report", { method: "POST", token, body }),
  checkin: (token, body) => request("/api/people/checkins", { method: "POST", token, body }),
  checkins: (token) => request("/api/people/checkins", { token }),
  endCheckin: (token, id) => request(`/api/people/checkins/${id}`, { method: "DELETE", token }),
  changePassword: (token, current_password, new_password) => request("/api/people/me/password", { method: "POST", token, body: { current_password, new_password } }),
};

export const push = {
  publicKey: () => request("/api/push/public-key"),
  subscribe: (token, sub) => request("/api/push/subscribe", { method: "POST", token, body: sub }),
  unsubscribe: (token, endpoint) => request("/api/push/unsubscribe", { method: "POST", token, body: { endpoint } }),
};

/** A "meet safely" check-in link, readable by anyone who has it — no sign-in. */
export const fetchCheckin = (token) => request(`/api/safety/${token}`);

export const adminPeople = {
  photos: (token) => request("/api/admin/people/photos", { admin: token }),
  approvePhoto: (token, id) => request(`/api/admin/people/photos/${id}/approve`, { method: "POST", admin: token }),
  rejectPhoto: (token, id) => request(`/api/admin/people/photos/${id}/reject`, { method: "POST", admin: token }),
  reports: (token) => request("/api/admin/people/reports", { admin: token }),
  resolve: (token, id, ban) => request(`/api/admin/people/reports/${id}/resolve`, { method: "POST", admin: token, body: { ban } }),
};
export const fetchEmergencyNumbers = (params) => request(`/api/emergency-numbers?${qs(params)}`);
export const bookings = {
  checkout: () => request("/api/bookings/checkout", { method: "POST" }).catch(() => {}),
  create: (body) => request("/api/bookings", { method: "POST", body }),
  get: (ref, token) => request(`/api/bookings/${encodeURIComponent(ref)}?${qs({ token })}`),
  cancel: (ref, token) => request(`/api/bookings/${encodeURIComponent(ref)}/cancel`, { method: "POST", body: { token } }),
  updateTickets: (ref, token, activities) => request(`/api/bookings/${encodeURIComponent(ref)}/activities`, { method: "PUT", body: { token, activities } }),
};
export const dealBookings = {
  create: (body) => request("/api/bookings/deal", { method: "POST", body }),
  cancel: (ref, token) => request(`/api/bookings/deal/${encodeURIComponent(ref)}/cancel`, { method: "POST", body: { token } }),
};
export const fetchTripWeather = (params) => request(`/api/trip-weather?${qs(params)}`);
