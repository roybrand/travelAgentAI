import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import product_rules, route_rules, showcase_routes, trip_rules

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
    returned = res.json()["request"]["day_areas"]
    assert returned[0] == {**day_areas[0], "radius_m": 5000, "types": []}


def test_showcase_route_seed_obeys_route_day_progression():
    req = {"destination": "PAR", "destinations": ["PAR", "ROM", "ATH"]}
    ideas = showcase_routes.route_ideas(req, 10)
    assert len(ideas) == 40
    expected_parts = ["morning", "afternoon", "evening", "night"]
    for day in range(1, 11):
        day_items = [item for item in ideas if item["fixed_day"] == day]
        assert [item["default_part"] for item in day_items] == expected_parts
        progresses = [item["route_progress"] for item in day_items]
        assert progresses == sorted(progresses)
        assert progresses[0] <= 0.2
        assert progresses[-1] >= 0.8
    globals_ = [item["global_route_progress"] for item in ideas]
    assert globals_ == sorted(globals_)


def test_showcase_itinerary_returns_canonical_route_days(client):
    res = client.post("/api/plan-trip", json={**VALID_REQUEST, "destination": "PAR", "destinations": ["PAR", "ROM", "ATH"]})
    assert res.status_code == 200
    route_days = res.json()["itinerary"]["route_days"]
    planning_rules = res.json()["itinerary"]["planning_rules"]
    validation = res.json()["itinerary"]["validation"]
    assert planning_rules["valid"] is True
    assert planning_rules["retrieved"]
    assert validation["valid"] is True
    assert validation["source_quality"]["flights"] == "demo"
    assert "flights_source_quality:demo" in validation["warnings"]
    assert any(r["source"] == "docs/ROUTE_DAY_BUSINESS_RULES.md" for r in planning_rules["retrieved"])
    assert len(route_days) == 10
    assert route_days[0]["completed_path"] == []
    assert route_days[1]["completed_path"]
    for day in route_days:
        assert not day["violations"]
        assert [slot["part"] for slot in day["slots"]] == ["morning", "afternoon", "evening", "night"]
        assert len(day["active_path"]) >= 5
        progresses = [slot["route_progress"] for slot in day["slots"]]
        assert progresses == sorted(progresses)
        assert day["slots"][0]["distance_from_day_start_m"] is not None
        assert day["slots"][-1]["distance_from_previous_stop_m"] is not None


def test_product_rule_retrieval_finds_route_day_rules():
    found = product_rules.retrieve("route day previous gray morning night distance")
    assert found
    assert found[0]["source"] == "docs/ROUTE_DAY_BUSINESS_RULES.md"


def test_route_day_overrides_are_deterministically_validated():
    itinerary = {
        "route": [
            {"city": "Start", "lat": 0, "lng": 0},
            {"city": "End", "lat": 0, "lng": 1},
        ],
        "guide": {
            "by_type": {
                "route": {
                    "places": [
                        {"key": "a", "name": "A", "day": 1, "default_part": "morning", "route_progress": 0.95},
                        {"key": "b", "name": "B", "day": 1, "default_part": "night", "route_progress": 0.05},
                        {"key": "c", "name": "C", "day": 1, "default_part": "evening", "route_progress": 0.6},
                        {"key": "d", "name": "D", "day": 1, "default_part": "afternoon", "route_progress": 0.35},
                    ]
                }
            }
        },
    }
    broken = route_rules.build_route_days(itinerary, {}, 1)[0]
    assert "morning_outside_route_band" in broken["violations"]
    assert "night_outside_route_band" in broken["violations"]
    fixed = route_rules.build_route_days({
        **itinerary,
        "route_day_overrides": {
            "a": {"part": "morning", "route_progress": 0.05},
            "b": {"part": "afternoon", "route_progress": 0.35},
            "c": {"part": "evening", "route_progress": 0.6},
            "d": {"part": "night", "route_progress": 0.95},
        },
    }, {}, 1)[0]
    assert fixed["violations"] == []
    assert [slot["key"] for slot in fixed["slots"]] == ["a", "b", "c", "d"]


def test_itinerary_validation_catches_cost_and_stay_contracts():
    req = {"start_date": "2026-01-01", "end_date": "2026-01-04", "budget": 500}
    itinerary = {
        "destination": "PAR",
        "destinations": ["PAR"],
        "flight": {"destination": "PAR", "total_price": 200},
        "stay_total_cost": 250,
        "total_cost": 999,
        "planning_rules": {"valid": True},
        "data_sources": [{"key": "flights", "mode": "amadeus"}, {"key": "stays", "mode": "estimate"}],
        "stay_segments": [
            {
                "destination": "PAR",
                "start_day": 1,
                "end_day": 2,
                "nights": 2,
                "check_in": "2026-01-01",
                "check_out": "2026-01-03",
                "hotel": {"id": "h1", "name": "Hotel", "price_source": "estimate"},
            }
        ],
        "partner_deals": [
            {"id": 7, "dest": "ROM", "category": "restaurant", "valid_from": "2026-01-01", "valid_to": "2026-01-04", "lat": 1, "lng": 1}
        ],
    }
    validation = trip_rules.validate_itinerary(itinerary, req, nights=3)
    assert validation["valid"] is False
    assert "total_cost_must_equal_flight_plus_stay" in validation["violations"]
    assert "stay:stay_segments_must_cover_trip_nights" in validation["violations"]
    assert "deal:deal_outside_trip_route:7" in validation["violations"]
    assert "stays_source_quality:estimate" in validation["warnings"]


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


def test_itinerary_exposes_trusted_handoff_boundaries(client):
    it = client.post("/api/plan-trip", json=VALID_REQUEST).json()["itinerary"]
    handoff = it["handoff"]
    assert handoff["model"] == "planner_handoff"
    assert handoff["flight"]["kind"] == "external_checkout"
    assert handoff["flight"]["owned_by_wayfinder"] is False
    assert handoff["stay"]["kind"] == "external_checkout"
    assert handoff["stay"]["owned_by_wayfinder"] is False
    assert handoff["local_marketplace"]["kind"] == "wayfinder_partner_vouchers"
    assert handoff["local_marketplace"]["owned_by_wayfinder"] is True


def test_itinerary_exposes_trip_aware_social_prompts(client):
    it = client.post("/api/plan-trip", json=VALID_REQUEST).json()["itinerary"]
    social = it["social"]
    assert social["positioning"].startswith("Use the itinerary")
    assert social["prompts"]
    first = social["prompts"][0]
    assert {"id", "title", "text", "activity_tag", "destination", "day", "part", "source"} <= set(first)
    assert any(p["activity_tag"] in {"nightlife", "food", "beach", "sightseeing"} for p in social["prompts"])
    assert len(social["days"]) == it["nights"]
    assert all(d["headline"].startswith("Light up Day") and d["prompts"] for d in social["days"])
    assert any(d["companions"] for d in social["days"])
    companion = next(d["companions"][0] for d in social["days"] if d["companions"])
    assert companion["demo"] is True and companion["request"] and companion["distance"] == "on your route"


def test_itinerary_lists_every_flight_option_labelled_and_includes_the_chosen_one(client):
    it = client.post("/api/plan-trip", json={"origin": "LON", "destination": "LIS", "start_date": "2026-11-10", "end_date": "2026-11-15", "travelers": 2}).json()["itinerary"]
    opts = it["flight_options"]
    assert len(opts) >= 2 and it["flight"]["id"] in {o["id"] for o in opts}
    assert opts[0]["labels"][0] == "Best value" and [o["score"] for o in opts] == sorted((o["score"] for o in opts), reverse=True)
    assert any("Cheapest" in o["labels"] for o in opts) and any("Fastest" in o["labels"] for o in opts)
    assert min(o["total_price"] for o in opts if "Cheapest" in o["labels"]) == min(o["total_price"] for o in opts)
