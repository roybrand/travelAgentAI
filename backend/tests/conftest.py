import os
import tempfile

# The suite must be deterministic and never touch the network or spend API credits, whatever is in
# backend/.env. Set before the app (and its MCP subprocess servers, which inherit the environment) loads.
os.environ["WAYFINDER_OFFLINE"] = "1"
# Partner accounts and deals go to a throwaway database, never the real backend/data/partners.db.
os.environ["WAYFINDER_DB"] = os.path.join(tempfile.mkdtemp(prefix="wayfinder-test-"), "partners.db")
os.environ["ADMIN_TOKEN"] = "test-admin-token-1234567890"
# To run the whole suite against PostgreSQL too, point WAYFINDER_TEST_DATABASE_URL at a throwaway database (it is
# emptied at the start). See scripts/test_postgres.sh, which starts one in Docker. Never a real database.
if os.environ.get("WAYFINDER_TEST_DATABASE_URL"):
    os.environ["WAYFINDER_DATABASE_URL"] = os.environ["WAYFINDER_TEST_DATABASE_URL"]
    from app.partners import db as _db  # noqa: E402

    _db.reset_postgres_for_tests()
else:
    os.environ.pop("WAYFINDER_DATABASE_URL", None)  # a production URL in the shell must never reach the tests

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # Entering the TestClient context runs the app's lifespan, which spawns the real
    # flights/hotels/guides MCP server subprocesses over stdio.
    with TestClient(app) as c:
        yield c
