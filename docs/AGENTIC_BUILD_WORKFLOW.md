# Agentic Build Workflow

When changing route planning behavior, use this order:

1. Capture the business rule in `docs/ROUTE_DAY_BUSINESS_RULES.md`.
2. Identify the source of truth: backend seed, backend API, frontend state, or frontend rendering.
3. Add or update an automated check for the rule where possible.
4. Change the source of truth before changing visual symptoms.
5. Build the frontend and run the focused backend tests.
6. Restart the dev server if hot reload could preserve stale state.
7. Verify the visible behavior against the rule, not only against the latest screenshot.

For route-day bugs, always inspect these in order:

1. `backend/app/showcase_routes.py` for seeded activity order and progress.
2. `frontend/src/state/TripContext.jsx` for saved schedule normalization.
3. `frontend/src/components/TripTimeline.jsx` for route-day suggestions, map paths, and distance labels.
4. `frontend/src/components/MapView.jsx` only after confirming the path data is correct.

