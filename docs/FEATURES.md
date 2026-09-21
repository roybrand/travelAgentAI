# Feature registry

Every feature of Wayfinder AI, in one place: what it does, whether it is built, what powers it, and where the
code lives. This file is the master record. **Add a line here whenever a feature is added.**

Two things keep it honest:

- A test (`backend/tests/test_nearby.py`) fails if any dynamic rule in the code is missing from the
  [dynamic features](#dynamic-features-created-at-runtime) table below.
- The app writes a **runtime log** of the dynamic features it actually fires, described in
  [the runtime log](#the-runtime-log).

**Status:** `Built` works today · `Optional` works when you add a key · `Fallback` used when a source is down · `Planned` not built

Related documents: [flows](01-system-flows.md), [architecture](02-architecture.md),
[technology and models](03-technology-and-models.md), [front end](04-frontend-and-visual-experience.md),
[live data and AI](05-live-data-and-ai.md).

---

## A. Trip planning core

| ID | Feature | Status | Powered by | Code |
|---|---|---|---|---|
| F-001 | Plan a trip from origin, destination, dates, budget, travelers and interests | Built | FastAPI, Pydantic | `app/main.py`, `app/schemas.py` |
| F-002 | Orchestration as a real graph; flights, stays and guide run in parallel | Built | LangGraph | `app/graph.py`, `app/nodes.py` |
| F-003 | Tool servers called by name over the MCP protocol (flights, hotels, guides) | Built | MCP Python SDK | `app/mcp_tools/` |
| F-004 | Weighted ranking of every flight and stay combination against price, quality, interests and budget | Built | Pure Python | `app/ranking/score.py`, `combine.py` |
| F-005 | Best pick plus three ranked alternatives | Built | Ranking | `app/ranking/combine.py` |
| F-006 | Pros and cons for the best pick and for each alternative, computed from the search numbers | Built | Ranking | `app/ranking/combine.py` |
| F-007 | Plain-language "why the agent chose this" rationale | Built | Rule-based text | `app/ranking/combine.py` |
| F-008 | Ranking copes with star class instead of guest ratings, never claiming reviews it does not have | Built | Ranking | `app/ranking/score.py` |
| F-009 | Budget tracking: within or over budget, per-person cost | Built | Ranking, UI | `app/nodes.py`, `pages/Trip.jsx` |

## B. Live data (free sources, no keys)

| ID | Feature | Status | Powered by | Code |
|---|---|---|---|---|
| F-010 | 100 selectable destinations: 40 Europe, 30 Americas, 30 Asia and the Middle East | Built | Curated catalog | `app/live/catalog.py` |
| F-011 | Destination dropdowns (From and To) grouped by region | Built | React | `components/DestSelect.jsx` |
| F-012 | Best time to go from five years of real weather, scored 1 to 5 per month | Built | Open-Meteo | `app/live/climate.py` |
| F-013 | Season verdict for your dates (Ideal, Good, Fair, Off-season) with a better-window tip | Built | Open-Meteo | `app/mcp_tools/guides_data.py` |
| F-014 | Real sights ranked by 30-day Wikipedia page views, junk filtered out | Built | Wikipedia | `app/live/places.py` |
| F-015 | Credited photos: only reuse-with-credit licences; author and licence on every image | Built | Wikimedia Commons | `app/live/places.py`, `components/Photo.jsx` |
| F-016 | Real hotels with star class, amenities, website and OpenStreetMap link | Built | OpenStreetMap | `app/live/osm.py` |
| F-017 | Hotel neighbourhood signals: bars, restaurants within 300 m, distance to beach and centre | Built | OpenStreetMap | `app/live/osm.py` |
| F-018 | Interest matching from those real signals (nightlife, food scene, beachfront, old town, spa, quiet, pet friendly) | Built | OpenStreetMap | `app/live/osm.py` |
| F-019 | Real restaurants near every sight, with real distances and no invented prices | Built | OpenStreetMap | `app/live/osm.py`, `app/live/guide.py` |
| F-020 | Overpass to Nominatim fallback for hotels and restaurants | Fallback | OpenStreetMap | `app/live/osm.py` |
| F-021 | Disk cache with stale-copy fallback and retry with backoff for flaky free APIs | Built | Local files | `app/live/http.py` |
| F-022 | Flight price estimates from distance, season and lead time, five fare shapes | Built | Pricing model | `app/live/pricing.py` |
| F-023 | Hotel price estimates from star class, city price level and season | Built | Pricing model | `app/live/pricing.py` |
| F-024 | Every price and data source labelled Live, Estimate or Demo in the UI | Built | UI | `components/SourceBadge.jsx` |
| F-025 | Real flight and hotel offers | Optional | Amadeus (free signup) | `app/live/amadeus.py` |
| F-026 | Offline demo fallback with simulated data, clearly labelled | Fallback | Generators | `app/mcp_tools/*_server.py` |
| F-027 | Hand-curated highlights and typical costs for Naples, Lisbon, Tokyo, Dubai | Built | Curated | `app/mcp_tools/guides_rich.py` |

## C. Visual app

| ID | Feature | Status | Powered by | Code |
|---|---|---|---|---|
| F-030 | Multi-page React app: Home, Your trip, Stays, Explore, Nearby, Credits | Built | React, Vite, React Router | `frontend/src/` |
| F-031 | Cinematic home with rotating destination photos and the search form | Built | React, Framer Motion | `pages/Home.jsx` |
| F-032 | "Agent is working" overlay showing the steps | Built | Framer Motion | `components/PlanningOverlay.jsx` |
| F-033 | Trip total with animated count-up, budget meter, cost donut | Built | Recharts | `pages/Trip.jsx` |
| F-034 | Day-by-day itinerary with photos, updating as you change stay or plan | Built | React state | `pages/Trip.jsx` |
| F-035 | Season chart with your trip highlighted and real temperatures on hover | Built | Recharts | `pages/Trip.jsx` |
| F-036 | Stays page: price vs area average chart, sort, map with price pins, photo galleries | Built | Recharts, Leaflet | `pages/Stays.jsx` |
| F-037 | Explore page: sight cards with photos, costs, nearby food, map, "add to my plan" | Built | Leaflet | `pages/Explore.jsx` |
| F-038 | Plan builder: choices on Stays and Explore change the trip total everywhere | Built | React context | `state/TripContext.jsx` |
| F-039 | Photo credits page; per-photo credit on hover | Built | React | `pages/Credits.jsx` |
| F-040 | Responsive layout for phones | Built | CSS | `styles.css` |
| F-041 | Data sources panel on the trip page | Built | UI | `pages/Trip.jsx` |

## D. AI (optional, needs an OpenAI key)

| ID | Feature | Status | Powered by | Code |
|---|---|---|---|---|
| F-050 | Plain-English trip request filled into the form, with assumptions shown | Optional | OpenAI | `app/live/llm.py`, `pages/Home.jsx` |
| F-051 | Model output validated: destination must be a catalog code, dates must be real and future | Built | Validation | `app/live/llm.py` |
| F-052 | Grounded trip summary; any text containing a number not in the facts is discarded, after one corrective retry | Optional | OpenAI + guard | `app/live/llm.py` |
| F-053 | **Trip builder**: describe a whole trip in words and the agent builds the profile and plans it in one step | Optional | OpenAI | `pages/Home.jsx`, `POST /api/build-trip` |
| F-054 | **Photo input**: add a picture of the vibe you like; a vision model reads its mood and activities (never identifies people) | Optional | OpenAI vision | `app/live/llm.py` |
| F-055 | **Traveler profile**: keywords, interests, vibe, pace, budget style and the place types you would enjoy; kept only in your browser and can be forgotten | Optional | OpenAI, browser storage | `lib/profile.js`, `pages/Trip.jsx` |
| F-056 | Photo privacy: shrunk to 768 px on your device, sent only for that request, size- and type-checked, never stored | Built | Browser canvas, validation | `lib/profile.js`, `app/live/llm.py` |
| F-057 | Numbers in AI text are matched by value, so "5 December" and "2026-12-05" agree | Built | Guard | `app/live/llm.py` |
| F-058 | Real places by type that you asked for: museums, art galleries, pubs and bars, nightclubs, parks, viewpoints, markets, historic sites, theatres, beaches, cafes, restaurants, spas, family attractions | Built | OpenStreetMap | `app/live/osm.py`, `pages/Explore.jsx` |
| F-059 | Opening hours and website shown when OpenStreetMap has them; never invented | Built | OpenStreetMap | `pages/Explore.jsx` |
| F-060a | **Compare your options**: three priced packages (Cheapest, Best match, Comfort) side by side with price-source labels | Built | Ranking | `app/nodes.py`, `pages/Trip.jsx` |

## E. Nearby now (opt-in, uses your location)

| ID | Feature | Status | Powered by | Code |
|---|---|---|---|---|
| F-060b | Master switch, off by default, with explicit privacy text; choice remembered on the device | Built | Browser storage | `pages/Nearby.jsx` |
| F-061 | Live position watching; refresh when you move about 150 m or after 10 minutes | Built | Browser Geolocation | `state/NearbyContext.jsx` |
| F-062 | Recommendations from your position: sights, restaurants, cafes, bars | Built | Wikipedia, OpenStreetMap | `app/live/nearby.py` |
| F-063 | Weather- and time-aware ranking (see the dynamic rules below) | Built | Open-Meteo | `app/live/nearby.py` |
| F-064 | Uses your trip plan: things you planned that are close by are surfaced first | Built | Trip context | `app/live/nearby.py` |
| F-065 | Pushes only new suggestions as in-app alerts; browser notification if you allow it | Built | Notifications API | `state/NearbyContext.jsx` |
| F-066 | Walking directions link and a live map with a "you are here" dot | Built | Leaflet | `pages/Nearby.jsx` |
| F-067 | Background push to a phone when the app is closed | Planned | Needs a service worker and push service | none |

## F. Quality and operations

| ID | Feature | Status | Powered by | Code |
|---|---|---|---|---|
| F-070 | Automated tests that never use the network or spend credits | Built | pytest, `WAYFINDER_OFFLINE=1` | `backend/tests/` |
| F-071 | Secrets in a git-ignored `.env`; nothing is sent to the browser | Built | `app/config.py` | `backend/.env.example` |
| F-072 | Photo pipeline for the four showcase cities | Built | Wikimedia Commons | `backend/scripts/fetch_photos.py` |
| F-073 | Diagrams and documentation for every layer | Built | Mermaid | `docs/` |

---

## Dynamic features (created at runtime)

These are decided by the app while it runs, from live conditions, not fixed in advance. Each has a stable ID.
They power the **Nearby now** page. Every time they fire, the app records it in the runtime log.

| Rule | What it does | Trigger |
|---|---|---|
| DYN-01 | Plan proximity: something from your trip plan is close to you right now | A planned item is within 3 km |
| DYN-02 | Rain expected or falling: indoor places are pushed up, open-air places down | Rain now, or 50% or more chance in the next 3 hours |
| DYN-03 | Good weather: parks, viewpoints and waterfronts are pushed up | Dry and 14 to 31 °C |
| DYN-04 | Breakfast time: cafes are pushed up | Local time 07:00 to 10:59 |
| DYN-05 | Lunch time: restaurants are pushed up | Local time 11:00 to 14:59 |
| DYN-06 | Evening: restaurants and bars are pushed up (bars more if you like nightlife) | Local time 17:00 to 22:59 |
| DYN-07 | Interest match: places that fit what you said you like are pushed up | Place tags overlap your interests |
| DYN-08 | Distance: nearer places rank higher, with a walking-time estimate | Always |
| DYN-09 | Popularity: among sights, more-read Wikipedia articles rank higher | Always |
| DYN-10 | No repeats: only a recommendation not already shown this session is pushed | Always |

### The runtime log

Whenever recommendations are generated, one row is appended to **`backend/logs/dynamic-features.md`**:
the time, the nearest city name, the conditions (dry or rain, local hour), which rules fired and how many
recommendations were produced. **It never contains coordinates.** The file is created on first use and is
git-ignored, because it is generated data, not source.

---

## Notes on the AI features

- **The key** lives in `backend/.env` (`OPENAI_API_KEY`). It is git-ignored and never sent to the browser. If a key is ever pasted into a chat or shared, treat it as exposed and rotate it.
- **Cost:** the default model is `gpt-4o-mini`. A trip build or summary costs a small fraction of a penny; a photo adds a little.
- **What the AI never does:** supply prices, availability or facts. It reads structured data we already have, or turns your words into form fields that are then validated.

## Not built yet

Rental cars, live restaurant and tour prices (no free source exists), guest reviews, bookings and payments,
user accounts and saved trips on a server, background push notifications, and a native mobile app.
