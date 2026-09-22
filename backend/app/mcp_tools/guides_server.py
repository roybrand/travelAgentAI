import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/, so `app.*` imports work when run as a script
from app import config  # noqa: E402
from app.live import catalog  # noqa: E402
from app.live.guide import build_live_guide  # noqa: E402
from app.mcp_tools.guides_data import build_guide  # noqa: E402

mcp = FastMCP("guides")


@mcp.tool()
def get_destination_guide(
    destination: str,
    start_date: str,
    end_date: str,
    interests: list[str] | None = None,
    place_types: list[str] | None = None,
) -> dict:
    """Return a guide for a destination: how suitable the traveler's dates are, the ideal months,
    top places and adventures (ranked by the traveler's interests), and practical tips.

    For the 109 catalog cities this is LIVE: real historical climate (Open-Meteo), sights and credited
    photos (Wikipedia/Wikimedia) and real nearby restaurants (OpenStreetMap). Showcase cities also keep
    their curated highlights. Falls back to the curated demo content when offline or if sources fail.
    `source` is "live" or "demo".
    """
    dest = catalog.resolve(destination)
    if dest and not config.offline():
        try:
            return build_live_guide(dest, start_date, end_date, interests or [], place_types or [])
        except Exception:
            pass  # fall through to the curated demo guide
    guide = build_guide(destination, start_date, end_date, interests)
    return {**guide, "source": "demo"}


if __name__ == "__main__":
    mcp.run()
