"""Runtime configuration.

Secrets live in backend/.env (never committed). Copy .env.example to .env and fill in what you have:

    OPENAI_API_KEY=sk-...            # optional: plain-English requests + grounded explanations
    OPENAI_MODEL=gpt-4o-mini         # optional
    OPENAI_BASE_URL=https://api.openai.com/v1   # optional: OpenAI-compatible endpoint
    AMADEUS_CLIENT_ID=...            # optional: real flight/hotel offers (free at developers.amadeus.com)
    AMADEUS_CLIENT_SECRET=...
    AMADEUS_BASE_URL=https://test.api.amadeus.com   # default; use the production URL once approved
    TICKETMASTER_API_KEY=...         # optional: live events and parties (free at developer.ticketmaster.com)
    TRAVELPAYOUTS_TOKEN=...          # optional: recent real flight fares (free affiliate signup at travelpayouts.com)
    ADMIN_TOKEN=...                  # required to use the moderation page (/admin); pick a long random string
    WAYFINDER_DB=...                 # optional: path of the partner/deals SQLite file (default backend/data/partners.db)

WAYFINDER_OFFLINE=1 disables every network call and uses the built-in demo data (the test suite sets it).
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # backend/
CACHE_DIR = ROOT / ".cache"


def load_env_file(path: Path | None = None) -> None:
    """Read KEY=VALUE lines into the environment without overriding variables that are already set."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()


def offline() -> bool:
    return os.environ.get("WAYFINDER_OFFLINE") == "1"


def openai_key() -> str | None:
    return None if offline() else (os.environ.get("OPENAI_API_KEY") or None)


def openai_base_url() -> str:
    """Override to use an OpenAI-compatible endpoint (a proxy, Azure, or a local fake for testing)."""
    return os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def openai_model() -> str:
    return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def amadeus_credentials() -> tuple[str, str] | None:
    if offline():
        return None
    cid, secret = os.environ.get("AMADEUS_CLIENT_ID"), os.environ.get("AMADEUS_CLIENT_SECRET")
    return (cid, secret) if cid and secret else None


def amadeus_base_url() -> str:
    return os.environ.get("AMADEUS_BASE_URL", "https://test.api.amadeus.com").rstrip("/")


def ticketmaster_key() -> str | None:
    return None if offline() else (os.environ.get("TICKETMASTER_API_KEY") or None)


def travelpayouts_token() -> str | None:
    return None if offline() else (os.environ.get("TRAVELPAYOUTS_TOKEN") or None)


def admin_token() -> str | None:
    """The moderation page is disabled until this is set. Deliberately not tied to offline mode."""
    return os.environ.get("ADMIN_TOKEN") or None


def db_path() -> Path:
    return Path(os.environ.get("WAYFINDER_DB") or ROOT / "data" / "partners.db")
