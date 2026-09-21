# Wayfinder AI: working rules

## Keep the markdown docs up to date, always

The docs are part of the product (they are shown to investors). Whenever you add or change something, update the
docs **in the same change**, not later:

1. **New feature or behaviour:** add a row to `docs/FEATURES.md` with a new F-number, its status, what powers it and
   where the code is. New nearby rules go in the DYN table. New runtime log events go in the partner activity table.
2. **Endpoint, page, nearby rule or `.env` variable:** run `python scripts/sync_docs.py` from `backend/`. It regenerates
   `docs/08-api-reference.md`. Never edit that file by hand. New settings also need a row in `docs/05-live-data-and-ai.md`.
3. **New backend module:** add it to the code map in `docs/02-architecture.md`.
4. **Bigger changes:** update the relevant numbered doc and its Mermaid diagrams. Diagrams must stay valid.
5. Run `python -m pytest` in `backend/`. `tests/test_docs_sync.py` and the other doc checks fail with a message saying
   which doc to update, so a green run means the docs are in step.

## Other rules

- Secrets live only in `backend/.env` (git-ignored). Never print, commit or log a key.
- Tests must never use the network or spend credits (`WAYFINDER_OFFLINE=1`, temp database).
- Partner deals are always labelled and never ranked by payment. Do not add any ranking input that reflects who pays.
- Do not commit unless asked. `backend/.env`, `backend/data`, `backend/logs`, `backend/.cache` and `frontend/dist` stay out of git.
