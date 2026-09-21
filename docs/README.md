# Wayfinder AI · Documentation

An AI trip planner: one request in, a ranked and explained flight + hotel itinerary out. Built on
FastAPI, LangGraph and MCP.

| Document | Answers |
|---|---|
| [01 · System flows](01-system-flows.md) | How does a request move through the system? User journey, sequence, LangGraph pipeline, ranking, refresh, errors, lifecycle |
| [02 · Architecture](02-architecture.md) | What are the pieces and how do they connect? Context, runtime, layers, code map, API, target architecture, roadmap |
| [04 · Front end and visual experience](04-frontend-and-visual-experience.md) | What does the app look like and how is it built? Page map, components, photo licensing, maps and deals, and exactly which numbers are real, computed, curated or simulated |
| [03 · Technology and models](03-technology-and-models.md) | What does each technology do, and how do the data, scoring, pros/cons and guide models work? Includes a worked scoring example |

## The system in one picture

```mermaid
flowchart LR
    U(["Traveler"]) --> UI["Web UI"]
    UI --> API["FastAPI"]
    API --> LG["LangGraph<br/>orchestrator"]
    LG --> MC["MCP client"]
    MC --> F[("Flights<br/>MCP server")]
    MC --> H[("Hotels<br/>MCP server")]
    MC --> D[("Guides<br/>MCP server")]
    LG --> R["Ranking<br/>engine"]
    R --> LG
    LG --> API --> UI

    style LG fill:#0f766e,color:#fff
    style F fill:#7c2d12,color:#fff
    style H fill:#7c2d12,color:#fff
    style D fill:#78350f,color:#fff
```

Orange = simulated or curated data source. Everything else is working code.

## Status at a glance

- **Working:** multi-page React app with photos, maps and charts, REST API with validation, LangGraph orchestration, three MCP tool servers (flights, hotels, destination guides), weighted ranking with a plain-language rationale, computed pros and cons, best-time-to-go assessment, 28 passing tests.
- **Simulated:** flight and hotel inventory (random data per request).
- **Curated, not live:** the destination guide (best months, places, adventures) is hand-written for 10 destinations.
- **Not yet built:** live provider APIs, LLM layer, RAG, database and accounts, rental cars, restaurants, attractions, mobile app. See the [roadmap](02-architecture.md#9-roadmap).

## Run it

```
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open http://localhost:8000. API docs at http://localhost:8000/docs.

The web app is a React build. Build it once with `cd frontend && npm install && npm run build`; see
[04](04-frontend-and-visual-experience.md#7-running-and-building) for the development workflow.

## Viewing the diagrams

Diagrams use Mermaid. They render automatically on GitHub. In VS Code, install the
*Markdown Preview Mermaid Support* extension, then open the Markdown preview.
