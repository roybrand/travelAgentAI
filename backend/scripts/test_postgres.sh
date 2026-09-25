#!/usr/bin/env sh
# Run the whole test suite against PostgreSQL, in Docker: a throwaway Postgres container plus the app image.
# Nothing touches a real database, and no Python packages are installed on this machine.
#   sh scripts/test_postgres.sh        (from backend/, with Docker running)
set -e
cd "$(dirname "$0")/../.."
# Git Bash on Windows rewrites paths handed to Docker; give Docker the real folder path and turn the rewriting off.
HERE="$(pwd -W 2>/dev/null || pwd)"
export MSYS_NO_PATHCONV=1
docker network create wf-test >/dev/null 2>&1 || true
docker rm -f wf-test-pg >/dev/null 2>&1 || true
docker run -d --name wf-test-pg --network wf-test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=wayfinder_test postgres:17-alpine >/dev/null
docker build -q -t wayfinder-test . >/dev/null
until docker exec wf-test-pg pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done
status=0
docker run --rm --network wf-test -u root \
  -e WAYFINDER_TEST_DATABASE_URL=postgresql://postgres:test@wf-test-pg:5432/wayfinder_test \
  -v "$HERE/backend/tests:/app/backend/tests:ro" -v "$HERE/docs:/app/docs:ro" \
  -v "$HERE/frontend/src:/app/frontend/src:ro" -v "$HERE/backend/scripts:/app/backend/scripts:ro" wayfinder-test \
  sh -c "python -m pytest -q -p no:cacheprovider" || status=$?
docker rm -f wf-test-pg >/dev/null
exit $status
