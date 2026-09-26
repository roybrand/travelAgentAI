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


def test_plan_trip_accepts_a_multi_stop_route(client):
    res = client.post("/api/plan-trip", json={**VALID_REQUEST, "destination": "PAR", "destinations": ["PAR", "ROM", "ATH"]})
    assert res.status_code == 200
    body = res.json()
    assert body["request"]["destination"] == "PAR"
    assert body["request"]["destinations"] == ["PAR", "ROM", "ATH"]
    assert body["itinerary"]["destinations"] == ["PAR", "ROM", "ATH"]
    assert [s["city"] for s in body["itinerary"]["route"]] == ["Paris", "Rome", "Athens"]
    stays = body["itinerary"]["stay_segments"]
    assert [s["destination"] for s in stays] == ["PAR", "ROM", "ATH"]
    assert sum(s["nights"] for s in stays) == 10
    assert all(s["hotel"] and s["hotel_options"] for s in stays)


def test_plan_trip_accepts_per_day_city_choices(client):
    day_locations = [
        {"day": 1, "destination": "PAR"},
        {"day": 2, "destination": "PAR"},
        {"day": 3, "destination": "ROM"},
        {"day": 4, "destination": "ROM"},
        {"day": 5, "destination": "ATH"},
        {"day": 6, "destination": "ATH"},
        {"day": 7, "destination": "ATH"},
        {"day": 8, "destination": "ATH"},
        {"day": 9, "destination": "ATH"},
        {"day": 10, "destination": "ATH"},
        {"day": 11, "destination": "ATH"},
    ]
    res = client.post("/api/plan-trip", json={**VALID_REQUEST, "destination": "PAR", "destinations": ["PAR", "ROM", "ATH"], "day_locations": day_locations})
    assert res.status_code == 200
    body = res.json()
    assert body["request"]["day_locations"] == day_locations
    stays = body["itinerary"]["stay_segments"]
    assert [(s["destination"], s["start_day"], s["end_day"], s["nights"]) for s in stays] == [
        ("PAR", 1, 2, 2),
        ("ROM", 3, 4, 2),
        ("ATH", 5, 10, 6),
    ]


def test_plan_trip_accepts_day_route_areas(client):
    day_areas = [{"day": 2, "country": "Australia", "label": "Adelaide to Coober Pedy to Alice Springs"}]
    res = client.post("/api/plan-trip", json={**VALID_REQUEST, "destination": "ADL", "destinations": ["ADL"], "day_areas": day_areas})
    assert res.status_code == 200
    assert res.json()["request"]["day_areas"] == day_areas


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


def test_config_and_destinations_endpoints(client):
    cfg = client.get("/api/config").json()
    assert cfg["offline"] is True and cfg["openai"] is False and cfg["destinations"] == 109
    data = client.get("/api/destinations").json()
    assert len(data["destinations"]) == 109 and data["regions"] == ["Europe", "Americas", "Asia", "Oceania"]


def test_parse_request_needs_an_openai_key(client):
    res = client.post("/api/parse-request", json={"text": "a week in Lisbon"})
    assert res.status_code == 503 and "OPENAI_API_KEY" in res.json()["detail"]


def test_parse_request_returns_validated_fields_when_enabled(client, monkeypatch):
    from app import main

    monkeypatch.setattr(main.llm, "enabled", lambda: True)
    monkeypatch.setattr(main.llm, "parse_trip_request", lambda text, today: {"destination": "LIS", "assumptions": []})
    res = client.post("/api/parse-request", json={"text": "a week in Lisbon"})
    assert res.status_code == 200 and res.json()["destination"] == "LIS"


def test_offline_itinerary_reports_demo_sources_and_no_ai_summary(client):
    it = client.post("/api/plan-trip", json=VALID_REQUEST).json()["itinerary"]
    assert [s["key"] for s in it["data_sources"]] == ["flights", "stays", "guide"]
    assert all(s["mode"] == "demo" for s in it["data_sources"])
    assert it["ai"] is None


def test_build_trip_endpoint_needs_a_key_and_validates_input(client, monkeypatch):
    from app import main

    assert client.post("/api/build-trip", json={"text": "a week in Lisbon"}).status_code == 503
    monkeypatch.setattr(main.llm, "enabled", lambda: True)
    assert client.post("/api/build-trip", json={"text": "hi"}).status_code == 422
    assert client.post("/api/build-trip", json={"text": "trip", "image": "http://x/y.jpg"}).status_code == 422
    monkeypatch.setattr(main.llm, "build_trip", lambda text, image, today: {"destination": "LIS", "profile": {"place_types": ["pub"]}})
    ok = client.post("/api/build-trip", json={"text": "pubs in Lisbon", "image": "data:image/jpeg;base64,/9j/4AAQ"})
    assert ok.status_code == 200 and ok.json()["profile"]["place_types"] == ["pub"]


def test_itinerary_offers_priced_packages_to_compare(client):
    it = client.post("/api/plan-trip", json=VALID_REQUEST).json()["itinerary"]
    assert it["packages"] and all({"labels", "total_cost", "vs_best", "price_sources"} <= set(p) for p in it["packages"])
    assert any("Best match" in p["labels"] for p in it["packages"])


def test_itinerary_lists_every_flight_option_labelled_and_includes_the_chosen_one(client):
    it = client.post("/api/plan-trip", json={"origin": "LON", "destination": "LIS", "start_date": "2026-11-10", "end_date": "2026-11-15", "travelers": 2}).json()["itinerary"]
    opts = it["flight_options"]
    assert len(opts) >= 2 and it["flight"]["id"] in {o["id"] for o in opts}
    assert opts[0]["labels"][0] == "Best value" and [o["score"] for o in opts] == sorted((o["score"] for o in opts), reverse=True)
    assert any("Cheapest" in o["labels"] for o in opts) and any("Fastest" in o["labels"] for o in opts)
    assert min(o["total_price"] for o in opts if "Cheapest" in o["labels"]) == min(o["total_price"] for o in opts)
