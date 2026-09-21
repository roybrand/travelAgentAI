# travel-agent-ai — vertical slice

A working end-to-end slice of the AI trip-planner described in [requirement.txt](requirement.txt):
submit a trip request → search flights → search hotels → rank/combine into a best pick with
alternatives and a plain-language rationale. Press "refresh" (call the endpoint again) and you
get a newly re-ranked plan, since every call re-runs the (mocked) provider searches.

**Scope of this slice**: flights + hotels only. Rental cars, restaurants, attractions, RAG,
a database, auth, and the mobile frontend are intentionally out — see "Not built yet" below.

## Why this isn't Python/FastAPI/LangGraph/MCP-SDK, per the requirement doc

This environment has no Python installed, and neither the public npm registry nor the
corporate Artifactory registry configured in `npm config` (`jfrog.apps.ocplanp.clalit.org.il`,
unreachable from here) is reachable, so no third-party packages could be installed. This slice
is therefore **plain Node.js (built-in modules only)** — no dependencies, `node --test` for
tests. Nothing here needs `npm install` to run.

To keep a real upgrade path, the pieces that stand in for LangGraph/MCP mirror their shapes:

| This slice | Real thing later | File |
|---|---|---|
| `StateGraph` (nodes + edges + shared state) | `@langchain/langgraph`'s `StateGraph` | [src/graph/stateGraph.js](src/graph/stateGraph.js) |
| `ToolRegistry` (name + schema + handler, called by name) | `@modelcontextprotocol/sdk` tool server/client | [src/mcp/toolRegistry.js](src/mcp/toolRegistry.js) |
| Mock `searchFlights`/`searchHotels` | Amadeus/Skyscanner, Booking.com/Airbnb MCP tools | [src/mcp/tools/](src/mcp/tools/) |

Once you have registry access on a machine that can `npm install`, the node functions in
[src/graph/nodes.js](src/graph/nodes.js) can be rewired onto real `StateGraph`/MCP client
instances largely unchanged — the swap is in the wiring ([src/graph/graph.js](src/graph/graph.js),
[src/mcp/registry.js](src/mcp/registry.js)), not the business logic.

## Run it

```
node src/server.js
```

Then:

```
curl -X POST http://localhost:3000/api/plan-trip \
  -H "Content-Type: application/json" \
  -d '{
    "origin": "LON",
    "destination": "NAP",
    "startDate": "2026-09-10",
    "endDate": "2026-09-20",
    "budget": 2500,
    "travelers": 2,
    "interests": ["beachfront", "nightlife", "michelin-nearby"]
  }'
```

Call it again to "refresh" — mock prices/availability re-roll each time, so you'll get a
different ranked plan.

## Test it

```
npm test
```

15 tests covering the graph engine, the ranking/combination math, and the HTTP API
(validation, happy path, refresh, 404s).

## How ranking works

See [src/ranking/score.js](src/ranking/score.js) and [src/ranking/combine.js](src/ranking/combine.js).
Flights are scored on price + duration; hotels on price + rating + how many of your `interests`
match the hotel's tags. The top 3 flights × top 3 hotels are combined, each combo's total cost is
checked against `budget`, and the highest-scoring combo wins — mirroring the "score price,
distance, ratings, interests... not just cheapest" idea in the requirement doc. The rationale
array explains the top pick versus the runner-up hotel (price/rating/interest-match deltas).

## Not built yet (deliberately out of scope for this slice)

- Rental cars, restaurants, attractions, routes/traffic, weather, events
- RAG / vector store (travel guides, visa rules, user preferences)
- Persistence (Postgres), auth, notifications, background jobs
- Mobile frontend
- Real provider integrations (all data here is mocked/randomized)
- Real LangGraph.js / MCP SDK (blocked on package installation, see above)
