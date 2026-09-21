from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .graph import build_trip_planning_graph
from .mcp_tools.client import MCPToolClient
from .schemas import TripRequest


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
SPA_ROUTES = ("trip", "stays", "explore", "credits")  # client-side routes served by the React app

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
    }

    result = await app.state.graph.ainvoke({"request": request_dict, "nights": nights})

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "request": request_dict,
        "itinerary": result["itinerary"],
        "refresh_hint": "POST again to re-run the search with freshly refreshed mock prices/availability.",
    }
