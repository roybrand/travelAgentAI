import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .graph import build_trip_planning_graph
from .live import catalog, llm, nearby, nightlife
from .mcp_tools.client import MCPToolClient
from .partners.routes import router as partner_router
from .social.routes import router as people_router
from .social import demo_people
from .partners import demo_businesses, stripe_gateway
from .social import push
from .alerts import router as alerts_router
from .suppliers import ticketmaster, travelpayouts
from .schemas import BuildRequest, NearbyRequest, ParseRequest, TripRequest


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = MCPToolClient()
    await client.start()
    app.state.mcp_client = client
    app.state.graph = build_trip_planning_graph(client)
    try:  # keep the demo pools fresh; each does nothing if its demo data was never seeded
        if demo_people.exists():
            await asyncio.to_thread(demo_people.refresh_pool, True)
        if demo_businesses.exists():
            await asyncio.to_thread(demo_businesses.refresh, True)
    except Exception:
        pass
    try:
        yield
    finally:
        await client.stop()


app = FastAPI(title="travel-agent-ai backend", lifespan=lifespan)
app.include_router(partner_router)
app.include_router(people_router)
app.include_router(alerts_router)


STATIC_DIR = Path(__file__).parent / "static"
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
SPA_ROUTES = ("trip", "plan", "trips", "stays", "explore", "nearby", "tonight", "people", "alerts", "deals", "partners", "admin", "credits")  # client-side routes served by the React app

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
    # Never cached: the file's own name never changes across rebuilds (unlike the hashed JS/CSS it references),
    # so a cached copy of this exact page can silently keep pointing a browser at an old build.
    return FileResponse(_index_file(), headers={"Cache-Control": "no-cache"})


for _route in SPA_ROUTES:
    app.add_api_route(f"/{_route}", index, methods=["GET"], include_in_schema=False)

# Files that must live at the site root for the app to be installable and to show phone notifications.
ROOT_FILES = {
    "sw.js": "application/javascript", "manifest.webmanifest": "application/manifest+json",
    "icon-192.png": "image/png", "icon-512.png": "image/png", "apple-touch-icon.png": "image/png",
}


def _root_file(name: str):
    async def handler():
        path = FRONTEND_DIST / name
        if not path.exists():
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(path, media_type=ROOT_FILES[name], headers={"Cache-Control": "no-cache"})
    return handler


for _name in ROOT_FILES:
    app.add_api_route(f"/{_name}", _root_file(_name), methods=["GET"], include_in_schema=False)


@app.get("/health")
async def health():
    """Liveness check used by the UI status pill."""
    return {"status": "ok"}


@app.get("/api/config")
async def get_config():
    """What is switched on, so the UI can show or hide features and label data sources honestly."""
    return {
        "openai": llm.enabled(),
        "amadeus": bool(config.amadeus_credentials()),
        "ticketmaster": ticketmaster.enabled(),
        "travelpayouts": travelpayouts.enabled(),
        "payments": stripe_gateway.enabled(),
        "push": push.enabled(),
        "admin": bool(config.admin_token()),
        "offline": config.offline(),
        "destinations": len(catalog.DESTINATIONS),
    }


@app.get("/api/destinations")
async def destinations():
    """The 109 selectable destinations (Europe, Americas, Asia, Australia)."""
    return {"destinations": catalog.public_list(), "regions": [catalog.EUROPE, catalog.AMERICAS, catalog.ASIA, catalog.OCEANIA]}


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
    planned = [p.model_dump() for p in body.planned]
    try:
        fn = nearby.run_local if config.offline() else nearby.run
        return await asyncio.wait_for(
            asyncio.to_thread(fn, body.lat, body.lng, body.interests, planned, body.radius_m), timeout=60)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not look up places near you right now ({type(exc).__name__}).") from exc


@app.get("/api/tonight")
async def tonight(dest: str, day: date | None = Query(default=None, alias="date"), kinds: str = "clubs,bars"):
    """The best clubs and bars in a city for one night, with photos, opening hours, and real prices where they exist."""
    city = catalog.resolve(dest)
    if not city:
        raise HTTPException(status_code=404, detail="Unknown destination.")
    try:
        night = nightlife.valid_day(day)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    wanted = [k for k in kinds.split(",") if k in nightlife.KINDS]
    try:
        if config.offline():
            return await asyncio.to_thread(nightlife.run_local, city["code"], night)
        return await asyncio.wait_for(asyncio.to_thread(nightlife.run, city["code"], night, wanted), timeout=75)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not look up tonight's venues right now ({type(exc).__name__}).") from exc


@app.post("/api/plan-trip")
async def plan_trip(req: TripRequest):
    """Plan a trip: flights, stays, ranking, guide, packages, partner deals and an optional AI summary."""
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
