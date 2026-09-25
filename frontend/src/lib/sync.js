/** Bookkeeping for keeping trips and deal bookings in step with the traveler's account (browser only).
 *
 *   userId      which account this device last synced with (another account signing in starts clean)
 *   seq         how far through the account's changes this device has read
 *   pushed      "kind:id" -> the updatedAt last sent or received, so unchanged documents are not sent again
 *   tombstones  "kind:id" -> when it was deleted here, until the account has been told
 */
const KEY = "wf.sync.v1";
const EMPTY = { userId: null, seq: 0, pushed: {}, tombstones: {} };

export function loadSync() {
  try {
    return { ...EMPTY, ...(JSON.parse(localStorage.getItem(KEY) || "null") || {}) };
  } catch {
    return { ...EMPTY };
  }
}

export function storeSync(meta) {
  try {
    localStorage.setItem(KEY, JSON.stringify(meta));
  } catch {
    /* storage blocked: the next sync simply sends a little more */
  }
}

/** Remember that a document was deleted on this device, so the deletion reaches the account's other devices. */
export function recordDeletion(kind, id) {
  const meta = loadSync();
  meta.tombstones[`${kind}:${id}`] = new Date().toISOString();
  storeSync(meta);
}

export const resetSync = (userId) => storeSync({ ...EMPTY, userId });

/** Names, email and phone typed at checkout stay on this device: never part of what is synced. */
export function tripForSync(t) {
  if (!t.booking) return t;
  const { lead, others, ...booking } = t.booking; // eslint-disable-line no-unused-vars
  return { ...t, booking };
}

/** Keep this device's private checkout details when a newer copy of the trip arrives from the account. */
export function keepPrivate(local, remote) {
  if (!local?.booking || !remote.booking) return remote;
  return { ...remote, booking: { ...remote.booking, lead: local.booking.lead, others: local.booking.others } };
}
