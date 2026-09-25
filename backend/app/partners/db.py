"""Storage for everything the server keeps: partners, deals, People accounts, reservations, bookings, synced trips.

SQLite by default (no server, no cost: the laptop and the test suite), PostgreSQL in production: set
WAYFINDER_DATABASE_URL=postgresql://user:password@host:5432/dbname. The app's SQL is written once, SQLite-flavoured,
and translated for Postgres below (placeholders, INSERT OR IGNORE, ids of new rows). Changes to the schema are
numbered migrations (MIGRATIONS), applied once each and recorded in schema_migrations.
"""
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

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
    cancelled_at TEXT,
    tickets TEXT NOT NULL DEFAULT '[]'
);

-- Demo bookings of a single partner deal (app/bookings.py): which deal, which day, how many. Never who.
CREATE TABLE IF NOT EXISTS demo_deal_bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reference TEXT NOT NULL UNIQUE,
    token_hash TEXT NOT NULL,
    deal_id INTEGER NOT NULL,
    day TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    total REAL NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmed',
    created_at TEXT NOT NULL,
    cancelled_at TEXT,
    pay TEXT NOT NULL DEFAULT 'venue',
    voucher TEXT,
    part TEXT,
    redeemed_at TEXT
);
"""

_ready: set[str] = set()
_lock = threading.Lock()


# ---------------------------------------------------------------- migrations
# Numbered, applied once each, recorded in schema_migrations. SCHEMA above is version 0 (it only ever creates
# missing tables); every change after that is a migration here, never an edit to a table in SCHEMA. Each step must
# be safe on a database that already has part of it (the first two were once applied at start-up without a record).

def _columns(conn, dialect: str, table: str) -> set[str]:
    if dialect == "postgres":
        rows = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name = ?", (table,))
        return {r["column_name"] for r in rows}
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def _add_columns(conn, dialect: str, table: str, columns: dict[str, str]) -> None:
    have = _columns(conn, dialect, table)
    if not have:
        return  # the table doesn't exist in this database; SCHEMA creates it with every column
    for name, ddl in columns.items():
        if name not in have:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def _m1_columns_after_first_release(conn, dialect):
    _add_columns(conn, dialect, "users", {"gender": "TEXT", "show_age": "INTEGER NOT NULL DEFAULT 0",
                                          "audience_genders": "TEXT NOT NULL DEFAULT '[]'", "audience_ages": "TEXT NOT NULL DEFAULT '[]'",
                                          "under_review": "INTEGER NOT NULL DEFAULT 0"})
    _add_columns(conn, dialect, "intents", {"want_genders": "TEXT NOT NULL DEFAULT '[]'", "want_ages": "TEXT NOT NULL DEFAULT '[]'"})
    _add_columns(conn, dialect, "demo_bookings", {"tickets": "TEXT NOT NULL DEFAULT '[]'"})
    _add_columns(conn, dialect, "demo_deal_bookings", {"pay": "TEXT NOT NULL DEFAULT 'venue'", "voucher": "TEXT", "part": "TEXT", "redeemed_at": "TEXT"})


def _m2_voucher_index(conn, dialect):
    if _columns(conn, dialect, "demo_deal_bookings"):
        conn.execute("CREATE INDEX IF NOT EXISTS idx_deal_booking_voucher ON demo_deal_bookings (voucher)")


def _m3_account_docs(conn, dialect):
    """Trips and deal bookings kept with a traveler's account, so they follow them across devices. One row per
    document; `data` is the document as JSON text; `seq` rises with every write to a user's documents, so a device
    asks only for what changed since the last seq it saw. A deleted document stays as a tombstone so the deletion
    reaches the traveler's other devices."""
    if not _columns(conn, dialect, "users"):
        return
    conn.execute(
        "CREATE TABLE IF NOT EXISTS account_docs ("
        " user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
        " kind TEXT NOT NULL,"
        " doc_id TEXT NOT NULL,"
        " data TEXT NOT NULL,"
        " updated_at TEXT NOT NULL,"
        " seq INTEGER NOT NULL,"
        " deleted INTEGER NOT NULL DEFAULT 0,"
        " PRIMARY KEY (user_id, kind, doc_id))"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_account_docs_seq ON account_docs (user_id, seq)")


MIGRATIONS = [
    (1, "columns added after the first release", _m1_columns_after_first_release),
    (2, "index on deal booking vouchers", _m2_voucher_index),
    (3, "trips and deal bookings kept with the account", _m3_account_docs),
]


def _migrate(conn, dialect: str = "sqlite") -> None:
    """Apply every migration this database hasn't had yet, in order. Running it twice is harmless."""
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)")
    done = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
    for version, name, step in MIGRATIONS:
        if version in done:
            continue
        step(conn, dialect)
        conn.execute("INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                      (version, name, datetime.now(timezone.utc).isoformat()))


def schema_version() -> int:
    with tx() as c:
        return c.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0]


# ---------------------------------------------------------------- dialects

def dialect() -> str:
    return "postgres" if config.database_url() else "sqlite"


def is_unique_violation(exc: Exception) -> bool:
    """A duplicate on a UNIQUE column (for example an email already registered), on either database."""
    return "UNIQUE" in str(exc) or getattr(exc, "sqlstate", None) == "23505"


def postgres_schema() -> str:
    """SCHEMA in Postgres terms: auto-increment ids become SERIAL, REAL becomes DOUBLE PRECISION (REAL is only
    single precision on Postgres, which would round prices and coordinates)."""
    s = SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    return re.sub(r"\bREAL\b", "DOUBLE PRECISION", s)


# Tables with an integer `id` key: an INSERT into one gets "RETURNING id" on Postgres, so `cursor.lastrowid` works
# the same on both databases.
_ID_TABLES = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \(\s*id INTEGER PRIMARY KEY", SCHEMA))
_INSERT_TABLE = re.compile(r"^\s*INSERT\s+(?:OR\s+IGNORE\s+)?INTO\s+(\w+)", re.I)


def _to_postgres(sql: str, has_params: bool) -> tuple[str, bool]:
    """Translate the app's SQLite-flavoured SQL: ? placeholders, INSERT OR IGNORE, and ids of new rows."""
    if has_params:
        sql = sql.replace("%", "%%").replace("?", "%s")
    ignore = re.match(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO", sql, re.I)
    if ignore:
        sql = re.sub(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", sql, count=1, flags=re.I) + " ON CONFLICT DO NOTHING"
    m = _INSERT_TABLE.match(sql)
    returning = bool(m and m.group(1) in _ID_TABLES and "RETURNING" not in sql.upper())
    if returning:
        sql += " RETURNING id"
    return sql, returning


class Row:
    """A result row like sqlite3.Row: by column name or by position, and dict(row) works."""
    __slots__ = ("_values", "_index")

    def __init__(self, values, index):
        self._values = values
        self._index = index

    def __getitem__(self, key):
        return self._values[key] if isinstance(key, (int, slice)) else self._values[self._index[key]]

    def keys(self):
        return list(self._index)

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def __repr__(self):
        return f"Row({dict(zip(self._index, self._values))})"


def _row_factory(cursor):
    index = {d.name: i for i, d in enumerate(cursor.description or [])}
    return lambda values: Row(values, index)


class _PgCursor:
    def __init__(self, cur, returning: bool):
        self._cur = cur
        self.rowcount = cur.rowcount
        self.lastrowid = None
        if returning:
            first = cur.fetchone()
            self.lastrowid = first[0] if first else None

    def fetchone(self):
        return self._cur.fetchone() if self._cur.description else None

    def fetchall(self):
        return self._cur.fetchall() if self._cur.description else []

    def __iter__(self):
        return iter(self.fetchall())


class _PgConn:
    """A Postgres connection with the small part of the sqlite3 interface the app uses."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql: str, params=()):
        params = tuple(params or ())
        sql, returning = _to_postgres(sql, bool(params))
        cur = self._conn.cursor(row_factory=_row_factory)
        cur.execute(sql, params or None)
        return _PgCursor(cur, returning)

    def executescript(self, script: str):
        self._conn.execute(script)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()


_pool = None


def _pg_pool():
    """One connection pool per process (psycopg_pool when installed, else a new connection each time)."""
    global _pool
    if _pool is None:
        url = config.database_url()
        try:
            from psycopg_pool import ConnectionPool
            _pool = ConnectionPool(url, min_size=1, max_size=int(os.environ.get("WAYFINDER_DB_POOL", "10")), open=True)
            import atexit
            atexit.register(_pool.close)  # close its worker threads before the interpreter shuts down
        except ImportError:
            import psycopg
            _pool = lambda: psycopg.connect(url)  # noqa: E731
    return _pool


@contextmanager
def _pg_connection():
    pool = _pg_pool()
    if callable(pool):
        conn = pool()
        try:
            yield conn
        finally:
            conn.close()
    else:
        with pool.connection() as conn:
            yield conn


def _init_postgres(conn: _PgConn) -> None:
    url = config.database_url()
    with _lock:
        if url in _ready:
            return
        conn.executescript(postgres_schema())
        _migrate(conn, "postgres")
        conn.commit()
        _ready.add(url)


def reset_postgres_for_tests() -> None:
    """Empty a Postgres test database completely (only ever used by the test suite)."""
    with _pg_connection() as raw:
        raw.execute("DROP SCHEMA public CASCADE")
        raw.execute("CREATE SCHEMA public")
        raw.commit()
    _ready.discard(config.database_url())


# ---------------------------------------------------------------- the one way the app talks to the database

def _init_sqlite(path: str, conn: sqlite3.Connection) -> None:
    with _lock:
        if path in _ready:
            has_tables = conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'schema_migrations'").fetchone()
            if has_tables:
                return  # the file may have been deleted or replaced while the server ran
        conn.executescript(SCHEMA)
        _migrate(conn, "sqlite")
        conn.commit()
        _ready.add(path)


@contextmanager
def tx():
    """One transaction: committed on success, rolled back on error. SQLite unless WAYFINDER_DATABASE_URL is set."""
    if config.database_url():
        with _pg_connection() as raw:
            conn = _PgConn(raw)
            _init_postgres(conn)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return
    path = config.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _init_sqlite(str(path), conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
