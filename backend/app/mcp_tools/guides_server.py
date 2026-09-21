from mcp.server.fastmcp import FastMCP

from guides_data import build_guide  # sibling module: this file runs as a script, so its dir is on sys.path

mcp = FastMCP("guides")


@mcp.tool()
def get_destination_guide(
    destination: str,
    start_date: str,
    end_date: str,
    interests: list[str] | None = None,
) -> dict:
    """Return a curated guide for a destination: how suitable the traveler's dates are,
    the ideal months to visit, top places and adventures (ranked by the traveler's
    interests), and practical tips.

    Curated prototype content standing in for a RAG-backed travel knowledge base.
    Returns {"found": false} for destinations without a guide.
    """
    return build_guide(destination, start_date, end_date, interests)


if __name__ == "__main__":
    mcp.run()
