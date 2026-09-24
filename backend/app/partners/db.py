"""SQLite storage for partner accounts, sessions and deals.

SQLite needs no server and no cost, which suits a prototype. The schema is plain SQL, so moving to
Postgres later is a driver swap rather than a redesign. The file lives in backend/data/ (git-ignored).
"""
import sqlite3
import threading
from contextlib import contextmanager

from app import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS partners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    business_type TEXT NOT NULL,
    city TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    api_key_hash TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    partner_id INTEGER NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    partner_id INTEGER NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
    external_id TEXT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    dest TEXT NOT NULL,
    lat REAL,
    lng REAL,
    address TEXT,
    price REAL NOT NULL,
    reference_price REAL,
    currency TEXT NOT NULL,
    price_note TEXT,
    valid_from TEXT NOT NULL,
    valid_to TEXT NOT NULL,
    stock INTEGER,
    url TEXT NOT NULL,
    terms TEXT NOT NULL,
    photo_url TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'pending',
    paused INTEGER NOT NULL DEFAULT 0,
    reject_reason TEXT,
    content_hash TEXT NOT NULL,
    impressions INTEGER NOT NULL DEFAULT 0,
    clicks INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    UNIQUE (partner_id, external_id)
);
CREATE INDEX IF NOT EXISTS idx_deals_lookup ON deals (status, dest, valid_to);

-- Featured deal placements: a partner pays (real Stripe Checkout) to pin an approved deal in a labelled
-- "Featured" strip for a city for a week. The only thing money buys; deals.rank_deals never sees it.
CREATE TABLE IF NOT EXISTS featured_deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_id INTEGER NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    partner_id INTEGER NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending',
    amount_cents INTEGER NOT NULL,
    currency TEXT NOT NULL,
    starts_at TEXT,
    ends_at TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_featured_active ON featured_deals (status, ends_at);

-- People: travelers who meet at places (see app/social). Kept in the same file, separate from partners.
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    birth_year INTEGER NOT NULL,
    bio TEXT NOT NULL DEFAULT '',
    interests TEXT NOT NULL DEFAULT '[]',
    languages TEXT NOT NULL DEFAULT '[]',
    home_city TEXT,
    photo_file TEXT,
    photo_status TEXT NOT NULL DEFAULT 'none',
    visible INTEGER NOT NULL DEFAULT 1,
    gender TEXT,
    show_age INTEGER NOT NULL DEFAULT 0,
    audience_genders TEXT NOT NULL DEFAULT '[]',
    audience_ages TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    demo INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS attendances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    place_key TEXT NOT NULL,
    place_name TEXT NOT NULL,
    place_type TEXT,
    dest TEXT NOT NULL,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    day TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (user_id, place_key, day)
);
CREATE INDEX IF NOT EXISTS idx_attend_place ON attendances (place_key, day);
CREATE TABLE IF NOT EXISTS intents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    tags TEXT NOT NULL,
    languages TEXT NOT NULL DEFAULT '[]',
    vibes TEXT NOT NULL DEFAULT '[]',
    want_genders TEXT NOT NULL DEFAULT '[]',
    want_ages TEXT NOT NULL DEFAULT '[]',
    summary TEXT NOT NULL,
    day TEXT NOT NULL,
    part TEXT NOT NULL DEFAULT 'any',
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    radius_m INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_intents_open ON intents (status, day);
CREATE TABLE IF NOT EXISTS connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_user INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    to_user INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    responded_at TEXT,
    UNIQUE (from_user, to_user)
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connection_id INTEGER NOT NULL REFERENCES connections(id) ON DELETE CASCADE,
    sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conn ON messages (connection_id, id);
-- Web Push subscriptions, tied to a Wayfinder People account -- the one durable identity in this app, and
-- the natural place for "notify me even when the app is closed" to live.
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint TEXT NOT NULL UNIQUE,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_push_user ON push_subscriptions (user_id);
CREATE TABLE IF NOT EXISTS blocks (
    blocker_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    blocked_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (blocker_id, blocked_id)
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    target_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message_id INTEGER,
    reason TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL
);

-- "Meet safely": a link a person can share outside the app (a friend, a family member) with what they told us
-- about a planned meetup. Deliberately coarse: a place description they typed, not coordinates.
CREATE TABLE IF NOT EXISTS safety_checkins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    connection_id INTEGER REFERENCES connections(id) ON DELETE SET NULL,
    other_name TEXT NOT NULL,
    other_photo_url TEXT,
    place_text TEXT NOT NULL,
    meet_at TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    revoked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_checkin_token ON safety_checkins (token);

-- A queryable mirror of the activity log (see app/partners/activity.py): the same fixed-vocabulary events,
-- grouped by day for charts instead of only readable as markdown. Never a name, email or coordinate -- the
-- same promise the markdown log already makes.
CREATE TABLE IF NOT EXISTS analytics_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event TEXT NOT NULL,
    day TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_analytics_event_day ON analytics_events (event, day);

-- Demo bookings (app/bookings.py): the booking flow end to end with nothing reserved and nothing charged. Only
-- what the trip was, never who: no name, email or phone -- those stay in the traveler's browser. The manage token
-- is stored hashed, like session tokens.
CREATE TABLE IF NOT EXISTS demo_bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reference TEXT NOT NULL UNIQUE,
    token_hash TEXT NOT NULL,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    travelers INTEGER NOT NULL,
    activities INTEGER NOT NULL,
    flight_total REAL NOT NULL,
    stay_total REAL NOT NULL,
    activities_total REAL NOT NULL,
    total REAL NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmed',
    created_at TEXT NOT NULL,
    cancelled_at TEXT
);
"""

# Columns added after the first release. CREATE TABLE IF NOT EXISTS never alters an existing table, so these are
# added to databases created earlier.
_ADDED_COLUMNS = {
    "users": {"gender": "TEXT", "show_age": "INTEGER NOT NULL DEFAULT 0", "audience_genders": "TEXT NOT NULL DEFAULT '[]'",
              "audience_ages": "TEXT NOT NULL DEFAULT '[]'", "under_review": "INTEGER NOT NULL DEFAULT 0"},
    "intents": {"want_genders": "TEXT NOT NULL DEFAULT '[]'", "want_ages": "TEXT NOT NULL DEFAULT '[]'"},
}

_ready: set[str] = set()
_lock = threading.Lock()


def _migrate(conn: sqlite3.Connection) -> None:
    for table, columns in _ADDED_COLUMNS.items():
        have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, ddl in columns.items():
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def _init(path: str, conn: sqlite3.Connection) -> None:
    with _lock:
        if path in _ready:
            has_tables = conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'reports'").fetchone()
            if has_tables:
                return  # the file may have been deleted or replaced while the server ran
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
        _ready.add(path)


@contextmanager
def tx():
    """One connection, committed on success and rolled back on error."""
    path = config.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _init(str(path), conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
