import test from "node:test";
import assert from "node:assert/strict";
import { createServer } from "../src/server.js";

async function withServer(fn) {
  const server = createServer();
  await new Promise((resolve) => server.listen(0, resolve));
  const { port } = server.address();
  try {
    await fn(`http://127.0.0.1:${port}`);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

const validRequest = {
  origin: "LON",
  destination: "NAP",
  startDate: "2026-09-10",
  endDate: "2026-09-20",
  budget: 2500,
  travelers: 2,
  interests: ["beachfront", "nightlife", "michelin-nearby"],
};

test("GET /health returns ok", async () => {
  await withServer(async (base) => {
    const res = await fetch(`${base}/health`);
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { status: "ok" });
  });
});

test("POST /api/plan-trip with a valid request returns an itinerary", async () => {
  await withServer(async (base) => {
    const res = await fetch(`${base}/api/plan-trip`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(validRequest),
    });
    assert.equal(res.status, 200);

    const payload = await res.json();
    assert.equal(payload.itinerary.destination, "NAP");
    assert.equal(payload.itinerary.nights, 10);
    assert.ok(payload.itinerary.flight);
    assert.ok(payload.itinerary.hotel);
    assert.ok(Array.isArray(payload.itinerary.rationale));
    assert.ok(Array.isArray(payload.itinerary.alternatives));
    assert.deepEqual(payload._graphTrace, [
      "searchFlights", "searchHotels", "rankAndCombine", "buildItinerary",
    ]);
  });
});

test("POST /api/plan-trip rejects a request missing required fields", async () => {
  await withServer(async (base) => {
    const res = await fetch(`${base}/api/plan-trip`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ origin: "LON" }),
    });
    assert.equal(res.status, 400);

    const payload = await res.json();
    assert.match(payload.error, /Invalid trip request/);
    assert.ok(payload.details.length > 0);
  });
});

test("POST /api/plan-trip rejects malformed JSON", async () => {
  await withServer(async (base) => {
    const res = await fetch(`${base}/api/plan-trip`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{not json",
    });
    assert.equal(res.status, 400);
  });
});

test("pressing refresh (calling again) re-runs the search and can change the result", async () => {
  await withServer(async (base) => {
    const call = () => fetch(`${base}/api/plan-trip`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(validRequest),
    }).then((r) => r.json());

    const first = await call();
    const second = await call();

    assert.ok(first.itinerary.totalCost > 0);
    assert.ok(second.itinerary.totalCost > 0);
    assert.notEqual(first.generatedAt, second.generatedAt);
  });
});

test("unknown route returns 404", async () => {
  await withServer(async (base) => {
    const res = await fetch(`${base}/nope`);
    assert.equal(res.status, 404);
  });
});
