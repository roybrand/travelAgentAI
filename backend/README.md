# travel-agent-ai backend (Python)

The real-architecture port of the flights+hotels vertical slice: **FastAPI** +
**LangGraph** + the **MCP Python SDK**, matching the stack from
[../requirement.txt](../requirement.txt). This superseded the
[../node-slice/](../node-slice/) proof-of-concept, which was built only because
Python wasn't available in the original environment.

## What's real here (not mocked)

- **LangGraph** (`langgraph.graph.StateGraph`) — the actual orchestration graph, not
  a hand-rolled stand-in. See [app/graph.py](app/graph.py) / [app/nodes.py](app/nodes.py).
- **MCP** (`mcp` SDK) — flights and hotels are genuine MCP servers
  ([app/mcp_tools/flights_server.py](app/mcp_tools/flights_server.py),
  [app/mcp_tools/hotels_server.py](app/mcp_tools/hotels_server.py)), each spawned as
  its own subprocess and talked to over the stdio transport via a persistent
  `ClientSession` per server ([app/mcp_tools/client.py](app/mcp_tools/client.py)).
  Graph nodes call tools by name (`client.call("flights", "search_flights", ...)`) —
  they never import provider functions directly.
- **FastAPI** — request validation via Pydantic (`app/schemas.py`), auto docs at `/docs`.

## What's still mocked

Only the **data**: flight/hotel search results are randomly generated on every call
(no real Amadeus/Booking.com/etc. integration) — see the two MCP server files. The
protocol, orchestration, and process boundaries around that mock data are real.

## Run it

```
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Then open http://localhost:8000 for the web app (build it first with `cd ..rontend && npm install && npm run build`;
see [../docs/04-frontend-and-visual-experience.md](../docs/04-frontend-and-visual-experience.md)). Or call the API directly:

```
curl -X POST http://localhost:8000/api/plan-trip \
  -H "Content-Type: application/json" \
  -d '{
    "origin": "LON",
    "destination": "NAP",
    "start_date": "2026-09-10",
    "end_date": "2026-09-20",
    "budget": 2500,
    "travelers": 2,
    "interests": ["beachfront", "nightlife", "michelin-nearby"]
  }'
```

Interactive API docs: http://localhost:8000/docs

## Test it

```
.venv\Scripts\python.exe -m pytest -v
```

28 tests: ranking/scoring math (pure, no I/O) plus a `TestClient`-driven API suite
that runs the app's real lifespan — meaning the flights/hotels MCP subprocess servers
actually start for the API tests.

## Setup from scratch

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Not built yet

Same scope boundary as the Node slice: rental cars, restaurants, attractions,
routes/traffic, weather, events, RAG/vector store, persistence, auth, mobile
frontend, real provider integrations.
