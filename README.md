# travelAgentAi

AI trip-planner, built out incrementally from [requirement.txt](requirement.txt).

- **[backend/](backend/)** — primary implementation. FastAPI + real LangGraph + real
  MCP servers (flights/hotels), Python. Start here.
- **Live data:** 100 destinations (Europe, Americas, Asia) on free public sources, with optional Amadeus (real prices)
  and OpenAI (plain-English requests, grounded summaries). See [docs/05-live-data-and-ai.md](docs/05-live-data-and-ai.md).
- **[frontend/](frontend/)** — the traveler-facing web app: React + Vite, with real licensed destination
  photos, interactive maps, charts and a multi-page flow (Home, Your trip, Stays, Explore).
- **[docs/](docs/)** — flow charts, architecture diagrams, and technology/model explanations.
- **[node-slice/](node-slice/)** — earlier zero-dependency Node.js proof-of-concept,
  built before Python was available in the dev environment. Kept for reference; the
  Python backend is the one being carried forward.

Both implement the same vertical slice: submit a trip request (origin, destination,
dates, budget, interests) → search flights → search hotels → rank/combine into a best
pick with alternatives and a plain-language rationale. Not yet built: rental cars,
restaurants, attractions, RAG, persistence, auth, mobile frontend.

See [backend/README.md](backend/README.md) to run it, and [docs/](docs/README.md) for diagrams and the full explanation.
