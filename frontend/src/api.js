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
