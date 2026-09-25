"""Copy everything from the SQLite file into a PostgreSQL database, once, when moving to production.

    WAYFINDER_DATABASE_URL=postgresql://user:password@host:5432/db  python scripts/migrate_sqlite_to_postgres.py [path/to/partners.db]

The target is created from scratch with the app's own schema and migrations, so it must be empty: the script stops
if any table already has rows. Ids are kept (so links between rows stay intact) and each id counter is moved past
the highest copied id. Rows are copied in dependency order. The SQLite file is only read, never changed.

Rows whose link to another table is broken (for example a login session of a business that was deleted: older
SQLite connections did not enforce those links) are skipped and counted, never copied, and so is anything that
points at a skipped row (a message in a skipped conversation). Postgres always enforces these links.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app.partners import db  # noqa: E402

# Parents before children, so foreign keys are satisfied as rows arrive.
ORDER = [
    "partners", "sessions", "deals", "featured_deals", "users", "user_sessions", "attendances", "intents",
    "connections", "messages", "push_subscriptions", "blocks", "reports", "safety_checkins", "analytics_events",
    "demo_bookings", "demo_deal_bookings", "account_docs",
]


def main(path: str) -> None:
    if not config.database_url():
        sys.exit("Set WAYFINDER_DATABASE_URL to the target PostgreSQL database first.")
    src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    have = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    unknown = have - set(ORDER) - {"schema_migrations", "sqlite_sequence"}
    if unknown:
        sys.exit(f"These tables are not in the copy list yet, add them to ORDER: {sorted(unknown)}")

    with db.tx() as pg:  # creates the schema and runs every migration on the empty target
        for table in ORDER:
            if db._columns(pg, "postgres", table) and pg.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]:
                sys.exit(f"The target already has rows in {table}. Use an empty database.")

    copied, skipped = {}, {}
    kept = {}  # (table, column) -> values that were copied, so children can check their parent made it
    fks = {t: [(r["from"], r["table"], r["to"]) for r in src.execute(f"PRAGMA foreign_key_list({t})")] for t in ORDER if t in have}
    with db.tx() as pg:
        for table in ORDER:
            if table not in have:
                continue
            target_cols = db._columns(pg, "postgres", table)
            # (column, parent table, parent column) for every link from this table
            links = [(r["from"], r["table"], r["to"]) for r in src.execute(f"PRAGMA foreign_key_list({table})")]

            def linked(row):
                return all(row[col] is None or row[col] in kept.get((parent, pcol), set()) for col, parent, pcol in links)

            every = src.execute(f"SELECT * FROM {table}").fetchall()
            rows = [r for r in every if linked(r)]
            if len(rows) < len(every):
                skipped[table] = len(every) - len(rows)
            if not rows:
                copied[table] = 0
                continue
            cols = [c for c in rows[0].keys() if c in target_cols]
            sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
            for r in rows:
                pg.execute(sql, tuple(r[c] for c in cols))
            copied[table] = len(rows)
            for key in {pcol for _, parent, pcol in (fk for t in ORDER for fk in fks.get(t, [])) if parent == table} | {"id"}:
                if key in cols:
                    kept[(table, key)] = {r[key] for r in rows}
            if table in db._ID_TABLES:
                pg.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT COALESCE(MAX(id), 1) FROM {table}))")
    for table, n in copied.items():
        print(f"{table:22} {n}" + (f"   ({skipped[table]} orphaned rows skipped)" if table in skipped else ""))
    print("Done. Point the app at the new database with WAYFINDER_DATABASE_URL and restart it.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(config.db_path()))
