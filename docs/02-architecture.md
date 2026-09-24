# 02 · Architecture

Where the pieces live and how they connect. Diagrams marked **Current** describe what runs today.
The **Target** diagram shows the direction from [requirement.txt](../requirement.txt) and is not built.

**Contents**

1. [System context](#1-system-context-current)
2. [Runtime architecture](#2-runtime-architecture-current)
3. [Layered view](#3-layered-view-current)
4. [Code map](#4-code-map-current)
5. [Shared state and data flow](#5-shared-state-and-data-flow-current)
6. [API surface](#6-api-surface-current)
7. [Target architecture](#7-target-architecture-planned)
8. [What is real, estimated and demo](#8-what-is-real-estimated-and-demo)
9. [Roadmap](#9-roadmap)

---

## 1. System context (Current)

The system as a black box: who uses it and what it talks to.

```mermaid
flowchart LR
    U(["Traveler<br/>web browser"])
    subgraph SYS ["Wayfinder AI backend"]
        direction TB
        CORE["Trip planning service"]
    end
    P1[("Flights<br/>Amadeus or ESTIMATE")]
    P2[("Hotels + guide<br/>OpenStreetMap, Wikipedia,<br/>Open-Meteo: LIVE")]
    P3[("Amadeus, OpenAI<br/>OPTIONAL")]

    U -- "trip request (HTTP/JSON)" --> CORE
    CORE -- "itinerary (HTTP/JSON)" --> U
    CORE -- "MCP tool call" --> P1
    CORE -- "MCP tool call" --> P2
    CORE -- "MCP tool call" --> P3

    style CORE fill:#0f766e,color:#fff
    style P1 fill:#7c2d12,color:#fff
    style P2 fill:#7c2d12,color:#fff
    style P3 fill:#78350f,color:#fff
```

Orange marks estimated or optional parts. The live free sources are detailed in [05 · Live data and AI](05-live-data-and-ai.md).

---

## 2. Runtime architecture (Current)

What actually runs when you start the app: **one API process plus three tool-server processes**.

```mermaid
flowchart TB
    subgraph BROWSER ["Browser"]
        UI["React single-page app<br/>Vite build, served from /<br/>photos, charts, maps"]
    end

    subgraph P1 ["Process 1: uvicorn (Python)"]
        direction TB
        FA["FastAPI app<br/>routes, validation"]
        LG["LangGraph StateGraph<br/>5 nodes"]
        RK["Ranking engine<br/>score.py, combine.py"]
        MC["MCPToolClient<br/>persistent sessions"]
        FA --> LG
        LG --> RK
        LG --> MC
    end

    subgraph P2 ["Process 2: flights_server.py"]
        FS["FastMCP server<br/>tool: search_flights"]
    end

    subgraph P3 ["Process 3: hotels_server.py"]
        HS["FastMCP server<br/>tool: search_hotels"]
    end

    subgraph P4 ["Process 4: guides_server.py"]
        GS["FastMCP server<br/>tool: get_destination_guide"]
    end

    UI -- "HTTP  GET /  ·  POST /api/plan-trip  ·  GET /health" --> FA
    MC -- "MCP over stdio<br/>(JSON-RPC on stdin/stdout)" --> FS
    MC -- "MCP over stdio<br/>(JSON-RPC on stdin/stdout)" --> HS
    MC -- "MCP over stdio<br/>(JSON-RPC on stdin/stdout)" --> GS

    style P1 fill:#0b1f2e,color:#fff,stroke:#2dd4bf
    style P2 fill:#1e293b,color:#fff,stroke:#64748b
    style P3 fill:#1e293b,color:#fff,stroke:#64748b
    style P4 fill:#1e293b,color:#fff,stroke:#64748b
```

Why separate processes: each provider is isolated, so a slow or crashing provider cannot take down the
API. It also mirrors how production MCP servers behave, so swapping a mock for a real service changes
the server, not the orchestration.

---

## 3. Layered view (Current)

```mermaid
flowchart TB
    subgraph L1 ["Presentation"]
        A1["React web app<br/>frontend/ (Vite build)"]
        A2["Swagger UI<br/>/docs (auto-generated)"]
    end
    subgraph L2 ["API layer"]
        B1["FastAPI routes<br/>app/main.py"]
        B2["Request schema and validation<br/>app/schemas.py (Pydantic)"]
    end
    subgraph L3 ["Orchestration layer"]
        C1["Graph definition<br/>app/graph.py"]
        C2["Graph nodes<br/>app/nodes.py"]
        C3["Shared state<br/>app/state.py"]
    end
    subgraph L4 ["Domain layer"]
        D1["Scoring model<br/>app/ranking/score.py"]
        D2["Combination and rationale<br/>app/ranking/combine.py"]
    end
    subgraph L5 ["Tool / integration layer"]
        E1["MCP client<br/>app/mcp_tools/client.py"]
        E2["Flights MCP server"]
        E3["Hotels MCP server"]
        E4["Guides MCP server<br/>curated destination knowledge"]
    end

    L1 --> L2 --> L3
    L3 --> L4
    L3 --> L5

    style L1 fill:#0b1f2e,stroke:#2dd4bf,color:#fff
    style L2 fill:#0b1f2e,stroke:#2dd4bf,color:#fff
    style L3 fill:#0b1f2e,stroke:#2dd4bf,color:#fff
    style L4 fill:#0b1f2e,stroke:#2dd4bf,color:#fff
    style L5 fill:#0b1f2e,stroke:#2dd4bf,color:#fff
```

The domain layer (scoring) is pure Python with no I/O, which is why it is fully unit-tested without
starting any server.

---

## 4. Code map (Current)

```
travelAgentAi/
├── backend/                     Primary implementation (Python)
│   ├── app/
│   │   ├── main.py              FastAPI app, lifespan, routes
│   │   ├── schemas.py           TripRequest (Pydantic validation)
│   │   ├── state.py             TripState (shared LangGraph state)
│   │   ├── graph.py             StateGraph wiring: nodes and edges
│   │   ├── nodes.py             The five graph nodes
│   │   ├── ranking/
│   │   │   ├── score.py         Flight, hotel, and combination scoring
│   │   │   └── combine.py       Pairing, ranking, rationale, pros/cons
│   │   ├── live/                Live sources: catalog (109 cities), climate, places, osm, amadeus, llm, pricing,
│   │   │                        travel.py (flight and stay search: Amadeus, Travelpayouts, estimates), geo.py (distances), nearby, guide,
│   │   │                        nightlife.py (Tonight: best clubs and bars for one night),
│   │   │                        photos.py (finds a credited photo for activities, beaches, zoos and other photo-less items)
│   │   ├── partners/            The partner side, see doc 07
│   │   │   ├── db.py            SQLite schema and connections (backend/data/partners.db)
│   │   │   ├── security.py      scrypt passwords, hashed tokens and keys, rate limiter
│   │   │   ├── accounts.py      Sign-up, sessions, API keys, suspension
│   │   │   ├── deals.py         Deal validation, moderation, payment-blind ranking
│   │   │   ├── featured.py      Featured deal placements: the one thing money buys, kept out of ranking (see stripe_gateway.py)
│   │   │   ├── stripe_gateway.py  Optional real payment (Stripe Checkout + webhook signature verification), no SDK
│   │   │   ├── routes.py        The partner, moderation, feed, deals, events and payments endpoints
│   │   │   ├── demo_businesses.py  The labelled pool of 124 demo businesses, their daily deals and drawn pictures
│   │   │   └── activity.py      Runtime log of partner events (backend/logs/partner-activity.md)
│   │   ├── social/              Wayfinder People, see doc 09
│   │   │   ├── users.py         Traveler accounts (18+), profiles, photos, blocks
│   │   │   ├── moderation.py    Photo and text checks (OpenAI moderation, free) and photo validation
│   │   │   ├── places.py        Registering to places and seeing who is going
│   │   │   ├── intents.py       Reading a looking-for request and matching people
│   │   │   ├── connect.py       Connection requests, chat, reports, bans
│   │   │   ├── vocab.py         The fixed lists of activities, languages, vibes, genders and age bands, and the gender and age detectors
│   │   │   ├── demo_people.py   The labelled pool of 100 demo travelers: seeding, daily requests, dynamic matching, automated replies
│   │   │   ├── avatars.py       Illustrated avatars (SVG) for demo profiles
│   │   │   ├── safety.py        "Meet safely" check-in links: share a planned meetup outside the app, no sign-in to view
│   │   │   ├── push.py          Optional real Web Push (RFC 8291/8292), no SDK: subscriptions, encryption, and the send itself
│   │   │   └── routes.py        The /api/people, /api/push, /api/safety and /api/admin/people endpoints
│   │   ├── alerts.py            The radar: deal, person, request and message alerts, and the RSS feed
│   │   ├── suppliers/           Optional real-time adapters: ticketmaster.py (events), travelpayouts.py (fares)
│   │   ├── docsync.py           Generates docs/08-api-reference.md from the code
│   │   ├── mcp_tools/
│   │   │   ├── client.py        MCPToolClient (spawns and calls servers)
│   │   │   ├── flights_server.py  MCP server: search_flights (Amadeus / estimates, demo fallback)
│   │   │   ├── hotels_server.py   MCP server: search_hotels (OpenStreetMap, demo fallback)
│   │   │   ├── guides_server.py   MCP server: get_destination_guide
│   │   │   └── guides_data.py     Curated guides + best-time scoring
│   │   └── static/index.html    Fallback page (used if the React build is absent)
│   ├── scripts/fetch_photos.py   Downloads licensed photos from Wikimedia Commons
│   ├── scripts/sync_docs.py      Regenerates the API reference (a test fails if it is stale)
│   ├── scripts/seed_demo.py      Adds or removes clearly-labelled demo partners and deals
│   ├── scripts/seed_people.py    Adds or removes clearly-labelled demo travelers
│   ├── scripts/generate_demo_photos.py  Makes AI portraits of fictional people for the demo travelers (uses your OpenAI key)
│   └── tests/                   125+ tests: ranking, guides, live data, nearby, partners, API, docs in sync
├── frontend/                    React + Vite web app (pages, charts, maps, photos)
├── node-slice/                  Earlier zero-dependency Node.js proof of concept
├── docs/                        This documentation
└── requirement.txt              Original product brief
```

---

## 5. Shared state and data flow (Current)

`TripState` is the single object passed through the graph. Each node adds to it and never mutates
another node's output.

```mermaid
flowchart LR
    IN["Input<br/>request<br/>nights"] --> N1["search_flights"]
    N1 -- "+ flights" --> N2["search_hotels"]
    N2 -- "+ hotels" --> NG["destination_guide"]
    NG -- "+ guide" --> N3["rank_and_combine"]
    N3 -- "+ ranking" --> N4["build_itinerary"]
    N4 -- "+ itinerary" --> OUT["Output<br/>itinerary"]

    style IN fill:#334155,color:#fff
    style OUT fill:#0f766e,color:#fff
```

| Stage | State after the stage |
|---|---|
| Input | `request`, `nights` |
| After `search_flights` | + `flights` (list) |
| After `search_hotels` | + `hotels` (list) |
| After `destination_guide` | + `guide` (season fit, places, adventures; or `null`) |
| After `rank_and_combine` | + `ranking` (`chosen`, `alternatives`, `rationale`, pros and cons) |
| After `build_itinerary` | + `itinerary` (returned to the client) |

State lives only for the duration of one request. Nothing is persisted.

---

## 6. API surface (Current)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/`, `/trip`, `/stays`, `/explore`, `/credits` | The React app (client-side routes) |
| `GET` | `/assets/*`, `/photos/*` | Built JS/CSS and bundled destination photos |
| `POST` | `/api/plan-trip` | Plan a trip. Body: `TripRequest`. Returns the itinerary: best match, pros and cons, alternatives, destination guide |
| `GET` | `/health` | Liveness check (used by the UI's "Agents online" indicator) |
| `GET` | `/docs`, `/redoc`, `/openapi.json` | Auto-generated interactive API documentation |

---

## 7. Target architecture (Planned)

The end state described in the product brief. **Green = built today. Grey dashed = not built.**

```mermaid
flowchart TB
    subgraph CLIENT ["Clients"]
        WEB["Web UI"]:::built
        MOB["Mobile app<br/>Flutter"]:::planned
    end

    GW["API gateway and auth"]:::planned

    subgraph BRAIN ["AI orchestration (FastAPI + LangGraph)"]
        ORCH["Orchestrator graph"]:::built
        LLM["LLM planner<br/>intent, follow-ups, explanations"]:::planned
        RANK["Ranking engine"]:::built
        RAG["RAG retrieval<br/>guides, tips, preferences<br/>(replaces curated guides)"]:::planned
    end

    subgraph TOOLS ["MCP tool servers"]
        TF["Flights"]:::built
        TH["Hotels"]:::built
        TG["Destination guides<br/>curated content today"]:::built
        TC["Rental cars"]:::planned
        TR["Restaurants"]:::planned
        TA["Attractions and events"]:::planned
        TM["Maps and routes"]:::planned
        TW["Weather"]:::planned
    end

    subgraph EXT ["External providers"]
        X1["Amadeus / Skyscanner"]:::planned
        X2["Booking.com / Airbnb"]:::planned
        X3["Google Places / Yelp"]:::planned
        X4["Maps / Weather / Events APIs"]:::planned
    end

    subgraph DATA ["Data layer"]
        PG[("PostgreSQL<br/>users, trips, bookings")]:::planned
        VEC[("pgvector or Qdrant<br/>embeddings")]:::planned
        RED[("Redis<br/>price cache")]:::planned
    end

    JOBS["Background jobs<br/>Celery or Temporal<br/>price alerts, deal refresh"]:::planned

    WEB --> GW
    MOB --> GW
    GW --> ORCH
    ORCH --- LLM
    ORCH --> RANK
    ORCH --> RAG
    ORCH --> TF & TH & TG & TC & TR & TA & TM & TW
    TF -.-> X1
    TH -.-> X2
    TR -.-> X3
    TA -.-> X3
    TM -.-> X4
    TW -.-> X4
    RAG --> VEC
    ORCH --> PG
    ORCH --> RED
    JOBS --> ORCH

    classDef built fill:#0f766e,color:#fff,stroke:#2dd4bf
    classDef planned fill:#1e293b,color:#94a3b8,stroke:#475569,stroke-dasharray: 4 3
```

Stack choices come from [requirement.txt](../requirement.txt): Flutter, FastAPI, LangGraph, MCP,
pgvector or Qdrant, PostgreSQL, Redis, Celery or Temporal.

---

## 8. What is real, estimated and demo

| Area | Status | Detail |
|---|---|---|
| Web UI | Real | React + Vite multi-page app with photos, maps and charts. See [04](04-frontend-and-visual-experience.md) |
| REST API and validation | Real | FastAPI + Pydantic |
| Orchestration | Real | Actual LangGraph `StateGraph`, not a hand-rolled loop |
| Tool protocol | Real | Actual MCP SDK; servers run as separate processes over stdio |
| Ranking | Real | Deterministic weighted scoring, unit-tested |
| Weather, sights, photos, hotels, restaurants (109 cities) | **Live** | Open-Meteo, Wikipedia/Wikimedia, OpenStreetMap. Free, no keys |
| Flight and hotel **prices** | **Estimate**, or **Live** with Amadeus keys | Modelled from distance, star class, city level and season unless Amadeus is configured. Always labelled |
| Demo fallback | Simulated | Used only when live sources are unreachable, and labelled Demo |
| LLM | **Optional (OpenAI)** | Plain-English requests and grounded trip summaries when a key is set. Ranking and pros/cons stay rule-based |
| Destination guide (best time, places, adventures) | **Curated content** | Hand-written for 10 destinations, served through a real MCP tool. Not live data. This is the slot a RAG knowledge base fills later |
| Pros and cons | Real | Computed from the numbers in each search, not written by hand or by an LLM |
| RAG / vector store | Not built | |
| Persistence, accounts, bookings | Not built | Nothing is stored between requests |
| Nearby restaurants | **Live** | Real OpenStreetMap restaurants with real distances. No prices, reviews or discounts: free data has none |
| Destination photos | Real, licensed | Wikimedia Commons, credited in the app |
| Rental cars, live restaurants and attractions, routes, weather | Not built | |
| Mobile app | Not built | |

---

## 9. Roadmap

```mermaid
flowchart LR
    P0["Done<br/>Flights + hotels slice<br/>Pros and cons, best time to go,<br/>places and adventures<br/>LangGraph + MCP + FastAPI, Web UI"]:::done
    P1["Next<br/>Real provider APIs<br/>(flights, hotels)<br/>Redis price cache"]:::next
    P2["Then<br/>LLM layer: natural-language<br/>requests, richer explanations<br/>Rental cars + restaurants"]:::next
    P3["Later<br/>Live attractions, routes, weather<br/>RAG replaces curated guides<br/>PostgreSQL + accounts"]:::later
    P4["Later<br/>Mobile app<br/>Bookings and payments<br/>Price alerts (background jobs)"]:::later

    P0 --> P1 --> P2 --> P3 --> P4

    classDef done fill:#0f766e,color:#fff,stroke:none
    classDef next fill:#1e3a8a,color:#fff,stroke:none
    classDef later fill:#1e293b,color:#94a3b8,stroke:#475569
```
