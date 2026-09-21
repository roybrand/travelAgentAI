export async function planTrip(payload) {
  const res = await fetch("/api/plan-trip", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const j = await res.json();
      if (Array.isArray(j.detail)) detail = j.detail.map((d) => String(d.msg).replace(/^Value error, /, "")).join("; ");
      else if (j.detail) detail = j.detail;
    } catch {
      /* keep the generic message */
    }
    throw new Error(detail);
  }
  return res.json();
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
