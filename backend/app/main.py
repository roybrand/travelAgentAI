import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .graph import build_trip_planning_graph
from .live import catalog, llm, nearby
from .mcp_tools.client import MCPToolClient
from .schemas import BuildRequest, NearbyRequest, ParseRequest, TripRequest


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = MCPToolClient()
    await client.start()
    app.state.mcp_client = client
    app.state.graph = build_trip_planning_graph(client)
    try:
        yield
    finally:
        await client.stop()


app = FastAPI(title="travel-agent-ai backend", lifespan=lifespan)


STATIC_DIR = Path(__file__).parent / "static"
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
SPA_ROUTES = ("trip", "stays", "explore", "nearby", "credits")  # client-side routes served by the React app

if (FRONTEND_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")
    if (FRONTEND_DIST / "photos").exists():
        app.mount("/photos", StaticFiles(directory=FRONTEND_DIST / "photos"), name="photos")


def _index_file() -> Path:
    """The React build when present (npm run build in frontend/), else the simple fallback page."""
    built = FRONTEND_DIST / "index.html"
    return built if built.exists() else STATIC_DIR / "index.html"


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(_index_file())


for _route in SPA_ROUTES:
    app.add_api_route(f"/{_route}", index, methods=["GET"], include_in_schema=False)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/config")
async def get_config():
    """What is switched on, so the UI can show or hide features and label data sources honestly."""
    return {
        "openai": llm.enabled(),
        "amadeus": bool(config.amadeus_credentials()),
        "offline": config.offline(),
        "destinations": len(catalog.DESTINATIONS),
    }


@app.get("/api/destinations")
async def destinations():
    """The 100 selectable destinations (Europe, Americas, Asia)."""
    return {"destinations": catalog.public_list(), "regions": [catalog.EUROPE, catalog.AMERICAS, catalog.ASIA]}


@app.post("/api/parse-request")
async def parse_request(body: ParseRequest):
    """Turn a plain-English trip description into form fields (needs OPENAI_API_KEY)."""
    if not llm.enabled():
        raise HTTPException(status_code=503, detail="Plain-English requests need an OpenAI key. Add OPENAI_API_KEY to backend/.env.")
    try:
        return await asyncio.wait_for(asyncio.to_thread(llm.parse_trip_request, body.text, date.today()), timeout=45)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not understand that request ({type(exc).__name__}). Try the form instead.") from exc


@app.post("/api/build-trip")
async def build_trip(body: BuildRequest):
    """Trip fields plus a traveler profile (keywords, interests, place types) from free text and/or a photo."""
    if not llm.enabled():
        raise HTTPException(status_code=503, detail="The trip builder needs an OpenAI key. Add OPENAI_API_KEY to backend/.env.")
    if body.image and not llm.valid_image(body.image):
        raise HTTPException(status_code=422, detail="The photo must be a JPEG, PNG or WebP under about 1.5 MB.")
    if len(body.text.strip()) < 3 and not body.image:
        raise HTTPException(status_code=422, detail="Write a few words about the trip, or add a photo.")
    try:
        return await asyncio.wait_for(asyncio.to_thread(llm.build_trip, body.text, body.image, date.today()), timeout=60)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not build a trip from that ({type(exc).__name__}). Try the form instead.") from exc


@app.post("/api/nearby")
async def nearby_now(body: NearbyRequest):
    """Dynamic recommendations around a GPS position, using the weather, time of day, interests and trip plan."""
    if config.offline():
        return {"context": None, "recommendations": [], "notes": ["Offline mode: nearby recommendations need internet."],
                "generated_at": datetime.now(timezone.utc).isoformat()}
    planned = [p.model_dump() for p in body.planned]
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(nearby.run, body.lat, body.lng, body.interests, planned, body.radius_m), timeout=60)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not look up places near you right now ({type(exc).__name__}).") from exc


@app.post("/api/plan-trip")
async def plan_trip(req: TripRequest):
    nights = (req.end_date - req.start_date).days
    request_dict = {
        "origin": req.origin,
        "destination": req.destination,
        "start_date": req.start_date.isoformat(),
        "end_date": req.end_date.isoformat(),
        "budget": req.budget,
        "travelers": req.travelers,
        "interests": req.interests,
        "place_types": req.place_types,
    }

    result = await app.state.graph.ainvoke({"request": request_dict, "nights": nights})

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "request": request_dict,
        "itinerary": result["itinerary"],
        "refresh_hint": "POST again to re-run the search. Live sources are cached, so weather, sights and hotel locations change rarely.",
    }
