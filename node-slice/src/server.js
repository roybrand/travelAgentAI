import http from "node:http";
import { fileURLToPath } from "node:url";
import { validateTripRequest } from "./api/validateRequest.js";
import { buildTripPlanningGraph } from "./graph/graph.js";

const MAX_BODY_BYTES = 1_000_000;

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        reject(new Error("Request body too large"));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => {
      if (chunks.length === 0) return resolve({});
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString("utf8")));
      } catch {
        reject(new Error("Invalid JSON body"));
      }
    });
    req.on("error", reject);
  });
}

function sendJson(res, status, payload) {
  const body = JSON.stringify(payload, null, 2);
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8" });
  res.end(body);
}

export function createServer() {
  return http.createServer(async (req, res) => {
    if (req.method === "GET" && req.url === "/health") {
      return sendJson(res, 200, { status: "ok" });
    }

    if (req.method === "POST" && req.url === "/api/plan-trip") {
      let body;
      try {
        body = await readJsonBody(req);
      } catch (err) {
        return sendJson(res, 400, { error: err.message });
      }

      const { valid, errors, normalized } = validateTripRequest(body);
      if (!valid) {
        return sendJson(res, 400, { error: "Invalid trip request", details: errors });
      }

      try {
        const graph = buildTripPlanningGraph();
        const { state, trace } = await graph.invoke({ request: normalized });
        return sendJson(res, 200, {
          generatedAt: new Date().toISOString(),
          request: normalized,
          itinerary: state.itinerary,
          refreshHint: "POST again to re-run the search with freshly refreshed mock prices/availability.",
          _graphTrace: trace,
        });
      } catch (err) {
        return sendJson(res, 500, { error: "Trip planning failed", message: err.message });
      }
    }

    return sendJson(res, 404, { error: "Not found" });
  });
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  const port = Number(process.env.PORT) || 3000;
  createServer().listen(port, () => {
    console.log(`travel-agent-ai listening on http://localhost:${port}`);
    console.log(`POST /api/plan-trip  { origin, destination, startDate, endDate, budget?, travelers?, interests? }`);
  });
}
