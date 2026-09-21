import pytest
from fastapi.testclient import TestClient

from app.main import app

VALID_REQUEST = {
    "origin": "LON",
    "destination": "NAP",
    "start_date": "2026-09-10",
    "end_date": "2026-09-20",
    "budget": 2500,
    "travelers": 2,
    "interests": ["beachfront", "nightlife", "michelin-nearby"],
}


@pytest.fixture(scope="module")
def client():
    # Entering the TestClient context runs the app's lifespan, which spawns the
    # real flights/hotels MCP server subprocesses over stdio.
    with TestClient(app) as c:
        yield c


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_plan_trip_valid_request_returns_itinerary(client):
    res = client.post("/api/plan-trip", json=VALID_REQUEST)
    assert res.status_code == 200

    payload = res.json()
    itinerary = payload["itinerary"]
    assert itinerary["destination"] == "NAP"
    assert itinerary["nights"] == 10
    assert itinerary["flight"]
    assert itinerary["hotel"]
    assert isinstance(itinerary["rationale"], list)
    assert isinstance(itinerary["alternatives"], list)


def test_plan_trip_missing_required_fields_returns_422(client):
    res = client.post("/api/plan-trip", json={"origin": "LON"})
    assert res.status_code == 422


def test_plan_trip_end_date_before_start_date_returns_422(client):
    bad = {**VALID_REQUEST, "end_date": "2026-09-01"}
    res = client.post("/api/plan-trip", json=bad)
    assert res.status_code == 422


def test_refresh_reruns_search_and_can_change_result(client):
    first = client.post("/api/plan-trip", json=VALID_REQUEST).json()
    second = client.post("/api/plan-trip", json=VALID_REQUEST).json()

    assert first["itinerary"]["total_cost"] > 0
    assert second["itinerary"]["total_cost"] > 0
    assert first["generated_at"] != second["generated_at"]


def test_unknown_route_returns_404(client):
    res = client.get("/nope")
    assert res.status_code == 404


def test_itinerary_includes_pros_cons_and_destination_guide(client):
    itinerary = client.post("/api/plan-trip", json=VALID_REQUEST).json()["itinerary"]
    assert itinerary["pros"] and itinerary["cons"]
    assert all(alt["pros"] and alt["cons"] for alt in itinerary["alternatives"])

    guide = itinerary["guide"]
    assert guide["timing"]["verdict"] == "Ideal"  # NAP in September
    assert guide["places"] and guide["adventures"]


def test_unknown_destination_still_plans_without_a_guide(client):
    res = client.post("/api/plan-trip", json={**VALID_REQUEST, "destination": "ZZZ"})
    assert res.status_code == 200
    assert res.json()["itinerary"]["guide"] is None


def test_itinerary_exposes_all_hotels_with_visual_fields(client):
    it = client.post("/api/plan-trip", json=VALID_REQUEST).json()["itinerary"]
    options = it["hotel_options"]
    assert len(options) >= 5
    assert [o["score"] for o in options] == sorted((o["score"] for o in options), reverse=True)
    first = options[0]
    assert first["photos"] and first["amenities"] and len(first["price_history"]) == 30
    assert set(first["rating_breakdown"]) == {"Cleanliness", "Location", "Service", "Value"}
    assert it["hotel_price_stats"]["min"] <= it["hotel_price_stats"]["avg"] <= it["hotel_price_stats"]["max"]
    assert "lat" in first and "lng" in first  # NAP is a showcase destination


def test_showcase_guide_is_map_ready(client):
    guide = client.post("/api/plan-trip", json=VALID_REQUEST).json()["itinerary"]["guide"]
    assert guide["rich"] and guide["hero"] == "NAP-amalfi" and len(guide["center"]) == 2
    place = guide["places"][0]
    assert {"lat", "lng", "photo", "cost", "nearby"} <= set(place)
    assert all(v["distance_m"] <= 3000 for v in place["nearby"])
    assert guide["venues"]


def test_spa_routes_serve_the_app_but_unknown_routes_still_404(client):
    for route in ("/", "/trip", "/stays", "/explore", "/credits"):
        res = client.get(route)
        assert res.status_code == 200 and "text/html" in res.headers["content-type"], route
    assert client.get("/nope").status_code == 404
