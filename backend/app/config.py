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
    STRIPE_SECRET_KEY=...            # optional: real payment for Featured deal placements (free test-mode account at stripe.com)
    STRIPE_WEBHOOK_SECRET=...        # required alongside it, to trust Stripe's "payment completed" webhook
    VAPID_PUBLIC_KEY=...             # optional: real push notifications for messages and connection requests
    VAPID_PRIVATE_KEY=...            # generate a free pair: python scripts/generate_vapid_keys.py
    VAPID_SUBJECT=mailto:you@example.com   # required alongside the keys; a contact address for push services
    ADMIN_TOKEN=...                  # required to use the moderation page (/admin); pick a long random string
    WAYFINDER_DB=...                 # optional: path of the SQLite file (default backend/data/partners.db)
    WAYFINDER_DATABASE_URL=...       # production: postgresql://user:password@host:5432/db (then SQLite is not used)

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


def stripe_secret_key() -> str | None:
    return None if offline() else (os.environ.get("STRIPE_SECRET_KEY") or None)


def stripe_webhook_secret() -> str | None:
    return None if offline() else (os.environ.get("STRIPE_WEBHOOK_SECRET") or None)


def vapid_keys() -> tuple[str, str, str] | None:
    """(public, private, subject), or None until all three are set. Offline mode disables it like every
    other network-touching feature, even though sending a push is not "spending credits"."""
    if offline():
        return None
    pub, priv, sub = os.environ.get("VAPID_PUBLIC_KEY"), os.environ.get("VAPID_PRIVATE_KEY"), os.environ.get("VAPID_SUBJECT")
    return (pub, priv, sub) if pub and priv and sub else None


def admin_token() -> str | None:
    """The moderation page is disabled until this is set. Deliberately not tied to offline mode."""
    return os.environ.get("ADMIN_TOKEN") or None


def database_url() -> str | None:
    """PostgreSQL in production (postgresql://...). Unset: the SQLite file at db_path()."""
    url = (os.environ.get("WAYFINDER_DATABASE_URL") or "").strip()
    return url if url.startswith(("postgresql://", "postgres://")) else None


def db_path() -> Path:
    return Path(os.environ.get("WAYFINDER_DB") or ROOT / "data" / "partners.db")
