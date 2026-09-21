# 01 · System flows

How a trip request moves through the system, from the traveler's click to the itinerary on screen.
Every flow below reflects the code as it exists today (`backend/app/…`). Where something is
planned but not built, it is marked **(planned)**.

> Diagrams are [Mermaid](https://mermaid.js.org/). They render on GitHub and in VS Code with the
> *Markdown Preview Mermaid Support* extension.

**Contents**

1. [User journey](#1-user-journey)
2. [End-to-end request sequence](#2-end-to-end-request-sequence)
3. [The LangGraph pipeline](#3-the-langgraph-pipeline)
4. [Ranking decision flow](#4-ranking-decision-flow)
5. [The "Refresh" flow](#5-the-refresh-flow)
6. [Validation and error handling](#6-validation-and-error-handling)
7. [Application lifecycle](#7-application-lifecycle)
8. [Destination guide and pros/cons flow](#8-destination-guide-and-proscons-flow)

---

## 1. User journey

What the traveler does and sees.

```mermaid
flowchart TD
    A([Traveler opens the app]) --> B["Fills in trip details<br/>origin, destination, dates,<br/>budget, travelers, interests"]
    B --> C{"Details valid?<br/>(checked in the browser)"}
    C -- No --> D["Inline message,<br/>field highlighted"] --> B
    C -- Yes --> E["Presses 'Plan my trip'"]
    E --> F["Sees the agent working:<br/>flights, hotels, guide, ranking, itinerary"]
    F --> G{"Server response"}
    G -- Error --> H["Error message shown,<br/>form kept so they can retry"] --> B
    G -- Success --> I["Itinerary shown: best match, cost breakdown,<br/>pros and cons, rationale, alternatives,<br/>best time to go, places and adventures"]
    I --> J{"Not happy with the result?"}
    J -- "Presses 'Re-run search'" --> E
    J -- "Edits the form" --> B
    J -- No --> K([Traveler picks a plan])

    style A fill:#0f766e,color:#fff,stroke:none
    style K fill:#0f766e,color:#fff,stroke:none
    style I fill:#134e4a,color:#fff
```

> The "agent working" steps in the browser are a timed animation (about 1.7 s minimum). The real
> work is the single `POST /api/plan-trip` call; the browser does not yet receive per-step progress
> events. Streaming real progress is a natural next step.

---

## 2. End-to-end request sequence

Every actor that touches one request, in order.

```mermaid
sequenceDiagram
    autonumber
    actor U as Traveler
    participant UI as Browser UI<br/>(index.html)
    participant API as FastAPI<br/>POST /api/plan-trip
    participant G as LangGraph<br/>StateGraph
    participant MC as MCPToolClient
    participant FS as Flights MCP server<br/>(subprocess)
    participant HS as Hotels MCP server<br/>(subprocess)
    participant GS as Guides MCP server<br/>(subprocess)
    participant R as Ranking engine<br/>(score.py / combine.py)

    U->>UI: Press "Plan my trip"
    UI->>API: JSON {origin, destination, dates, budget, travelers, interests}
    API->>API: Validate with Pydantic (TripRequest)
    API->>API: nights = end_date - start_date
    API->>G: ainvoke({request, nights})

    G->>MC: call("flights", "search_flights", ...)
    MC->>FS: MCP CallToolRequest over stdio
    FS-->>MC: 4-6 flight options (JSON)
    MC-->>G: state.flights

    G->>MC: call("hotels", "search_hotels", ...)
    MC->>HS: MCP CallToolRequest over stdio
    HS-->>MC: 5-8 hotel options (JSON)
    MC-->>G: state.hotels

    G->>MC: call("guides", "get_destination_guide", ...)
    MC->>GS: MCP CallToolRequest over stdio
    GS-->>MC: timing verdict, places, adventures, tips (JSON)
    MC-->>G: state.guide

    G->>R: rank_and_combine(flights, hotels, nights, budget, interests)
    R-->>G: chosen combo + alternatives + rationale + pros/cons
    G->>G: build_itinerary
    G-->>API: state.itinerary

    API-->>UI: 200 {generated_at, request, itinerary}
    UI-->>U: Render best match, pros/cons, alternatives, best time, places
```

Key point: the graph nodes never import the flight or hotel code. They call tools **by name**
through the MCP client, so a real provider can replace a mock without touching the orchestration.

---

## 3. The LangGraph pipeline

The orchestration is a real `langgraph.graph.StateGraph` ([graph.py](../backend/app/graph.py)).
Each node reads from and writes to one shared state object ([state.py](../backend/app/state.py)).

```mermaid
flowchart LR
    S(["START<br/>state: request, nights"]) --> N1

    subgraph GRAPH ["LangGraph StateGraph: TripState"]
        direction LR
        N1["search_flights<br/><i>tool: flights.search_flights</i><br/>writes: flights"]
        N2["search_hotels<br/><i>tool: hotels.search_hotels</i><br/>writes: hotels"]
        NG["destination_guide<br/><i>tool: guides.get_destination_guide</i><br/>writes: guide"]
        N3["rank_and_combine<br/><i>pure Python scoring, pros/cons</i><br/>writes: ranking"]
        N4["build_itinerary<br/><i>shape the response</i><br/>writes: itinerary"]
        N1 --> N2 --> NG --> N3 --> N4
    end

    N4 --> E(["END<br/>state: itinerary"])

    N1 -. "MCP / stdio" .-> T1[("Flights<br/>MCP server")]
    N2 -. "MCP / stdio" .-> T2[("Hotels<br/>MCP server")]
    NG -. "MCP / stdio" .-> T3[("Guides<br/>MCP server")]

    style N1 fill:#1e3a8a,color:#fff
    style N2 fill:#1e3a8a,color:#fff
    style NG fill:#1e3a8a,color:#fff
    style N3 fill:#134e4a,color:#fff
    style N4 fill:#134e4a,color:#fff
    style T1 fill:#334155,color:#fff
    style T2 fill:#334155,color:#fff
    style T3 fill:#334155,color:#fff
```

| Node | Reads from state | Writes to state | How it works |
|---|---|---|---|
| `search_flights` | `request` | `flights` | Calls the flights MCP tool with origin, destination, dates, travelers |
| `search_hotels` | `request` | `hotels` | Calls the hotels MCP tool with destination, dates, travelers, interests |
| `destination_guide` | `request` | `guide` | Calls the guides MCP tool for season fit, places, adventures ([section 8](#8-destination-guide-and-proscons-flow)). If it fails or the destination has no guide, `guide` is `null` and the plan still completes |
| `rank_and_combine` | `flights`, `hotels`, `nights`, `request` | `ranking` | Scores and pairs the best options, then derives pros and cons ([section 4](#4-ranking-decision-flow)) |
| `build_itinerary` | `ranking`, `guide`, `request`, `nights` | `itinerary` | Assembles the response, sets `within_budget` |

Flights and hotels are independent, so today they run one after the other. They could run in
parallel and join before ranking; the code comment in `graph.py` notes this.

**When this grows (planned):** rental cars, restaurants and attractions become extra nodes with
their own MCP servers. A router node can then send follow-ups such as *"remove the rental car"* to
only the affected branch instead of re-running everything. This is where LangGraph's state model
pays off.

---

## 4. Ranking decision flow

What `rank_and_combine` does with the raw search results ([combine.py](../backend/app/ranking/combine.py)).
The scoring math is in [03 · Technology and models](03-technology-and-models.md#scoring-model).

```mermaid
flowchart TD
    A["Raw results<br/>4-6 flights, 5-8 hotels"] --> B["Score every flight<br/>60% price + 40% duration"]
    A --> C["Score every hotel<br/>35% price + 35% rating<br/>+ 30% interest match"]
    B --> D["Keep top 3 flights"]
    C --> E["Keep top 3 hotels"]
    D --> F["Form all pairings<br/>3 x 3 = 9 combinations"]
    E --> F
    F --> G["Score each combination<br/>30% flight + 50% hotel<br/>+ 20% budget fit"]
    G --> H["Sort by final score"]
    H --> I["Best = chosen pick"]
    H --> J["Next 3 = alternatives"]
    H --> K["Best combo with a different hotel<br/>= runner-up for comparison"]
    I --> L["Write rationale:<br/>total cost, airline, stops,<br/>price and rating vs runner-up,<br/>matched interests"]
    K --> L
    I --> PC["Derive pros and cons<br/>chosen pick vs. the averages found;<br/>each alternative vs. the chosen pick"]
    J --> PC
    L --> M
    PC --> M(["Return ranking"])
    J --> M
    I --> M

    style A fill:#334155,color:#fff
    style M fill:#0f766e,color:#fff,stroke:none
```

**Why not just pick the cheapest?** A slightly pricier combination that matches the traveler's
interests and rating expectations can outrank the cheapest one. That difference is the product's
core value over a plain price comparison.

---

## 5. The "Refresh" flow

The original brief: *"it is refreshed each time you press the button."*

```mermaid
flowchart LR
    A["Press<br/>'Plan my trip' or 'Re-run search'"] --> B["New POST /api/plan-trip"]
    B --> C["Graph re-runs from the start"]
    C --> D["Providers queried again"]
    D --> E["New results, re-ranked"]
    E --> F["New itinerary rendered"]
    F -. "next press" .-> A

    style D fill:#7c2d12,color:#fff
```

Nothing is cached or stored between presses, so each press is a fresh search. Today the providers
are mocks that generate new random prices and availability on every call, so results visibly change.
With real providers the same flow returns live prices. **(planned)** A cache layer would avoid
re-querying providers when nothing has changed.

---

## 6. Validation and error handling

```mermaid
flowchart TD
    A["POST /api/plan-trip"] --> B{"Pydantic validation<br/>TripRequest"}
    B -- "origin/destination empty<br/>end_date not after start_date<br/>budget not greater than 0<br/>travelers below 1<br/>bad date format" --> C["422 Unprocessable Entity<br/>with field-level errors"]
    B -- Valid --> D["Run LangGraph"]
    D --> E{"MCP tool call OK?"}
    E -- "result.isError" --> F["RuntimeError:<br/>MCP tool X on Y failed<br/>(surfaces as HTTP 500)"]
    E -- OK --> G["Rank and build itinerary"]
    G --> H["200 OK + itinerary"]

    C --> UI["UI shows the message,<br/>keeps the form"]
    F --> UI
    H --> R["UI renders the itinerary"]

    style C fill:#7f1d1d,color:#fff
    style F fill:#7f1d1d,color:#fff
    style H fill:#0f766e,color:#fff
```

The browser also validates before sending (missing fields, same origin and destination, return
before departure), so most mistakes never reach the server.

---

## 7. Application lifecycle

The three MCP servers are **long-lived processes**, started once with the API and reused for every
request, not launched per request.

```mermaid
sequenceDiagram
    autonumber
    participant OS as uvicorn
    participant APP as FastAPI lifespan
    participant MC as MCPToolClient
    participant FS as flights_server.py
    participant HS as hotels_server.py
    participant GS as guides_server.py

    OS->>APP: startup
    APP->>MC: start()
    MC->>FS: spawn subprocess (stdio)
    MC->>FS: initialize session
    MC->>HS: spawn subprocess (stdio)
    MC->>HS: initialize session
    MC->>GS: spawn subprocess (stdio)
    MC->>GS: initialize session
    APP->>APP: build_trip_planning_graph(client)
    Note over APP: Ready. /health returns ok.

    loop each request
        APP->>MC: call(server, tool, args)
        MC->>FS: reuse persistent session
    end

    OS->>APP: shutdown
    APP->>MC: stop()
    MC->>FS: close session and process
    MC->>HS: close session and process
    MC->>GS: close session and process
```

A single `AsyncExitStack` owns both sessions, so shutdown closes both cleanly even if one fails.

---

## 8. Destination guide and pros/cons flow

Two features that turn a ranked list into advice. They work differently, and the difference matters:

- **Pros and cons are computed.** Each line is derived from real numbers in *this* search.
- **The destination guide is curated.** It is hand-written knowledge served by the guides MCP tool, standing in for a future RAG knowledge base.

```mermaid
flowchart TD
    subgraph PC ["Pros and cons (computed per search)"]
        direction TB
        P1["Chosen pick vs. the averages<br/>of all flights and hotels found"] --> P2["Stops, price vs. average, journey time,<br/>rating, interest match, distance,<br/>budget gap, cost vs. cheapest combo"]
        P3["Each alternative vs. the chosen pick"] --> P4["Cost difference, stops, journey time,<br/>rating, interest match, distance"]
        P2 --> P5["Pros list + cons list"]
        P4 --> P5
    end

    subgraph GD ["Destination guide (curated knowledge)"]
        direction TB
        G1["Destination code<br/>e.g. NAP"] --> G2{"Guide exists?"}
        G2 -- No --> G3["guide = null<br/>UI says no guide yet"]
        G2 -- Yes --> G4["Average monthly suitability<br/>over every day of the trip"]
        G4 --> G5["Verdict: Ideal, Good, Fair<br/>or Off-season"]
        G4 --> G6["Ideal and worst windows<br/>e.g. May-Jun, Sep-Oct"]
        G5 --> G7{"Score well below<br/>the destination's best?"}
        G7 -- Yes --> G8["Suggest a better window"]
        G1 --> G9["Places and adventures,<br/>interest matches ranked first"]
    end

    style G3 fill:#334155,color:#fff
    style G8 fill:#7c2d12,color:#fff
```

**Best-time scoring.** Each destination stores a 1 to 5 suitability score per month (weather, crowds,
peak-season pressure). The trip is scored by averaging that value over **every day** of the trip, so a
trip that straddles two months is weighted correctly. Verdict thresholds: 4.5 and above is *Ideal*,
3.5 and above *Good*, 2.5 and above *Fair*, below that *Off-season*.

**Coverage today:** Naples/Amalfi, Lisbon, Tokyo, Dubai, Barcelona, Rome, Paris, Athens, New York and
Tel Aviv. Any other destination still gets a full ranked plan, just without the guide.
