"""Tests for the dynamic nearby-recommendations engine. Pure logic and fixtures: no network."""
from pathlib import Path

from app.live import nearby

HERE = (41.1496, -8.6110)
DRY = {"raining": False, "rain_soon": False, "temp_c": 22, "local_hour": 15}
RAIN = {"raining": False, "rain_soon": True, "temp_c": 12, "local_hour": 15}


def sight(id_, name, why, lat, lng, tags=(), views=500):
    return {"id": id_, "name": name, "why": why, "lat": lat, "lng": lng, "tags": list(tags), "views_30d": views, "url": "u"}


def food(id_, name, amenity, lat, lng, cuisine=""):
    return {"id": id_, "name": name, "amenity": amenity, "cuisine": cuisine, "lat": lat, "lng": lng}


MUSEUM = sight("s1", "City Museum", "Art museum", 41.1500, -8.6110)   # ~45 m
PARK = sight("s2", "Crystal Garden", "Public park", 41.1497, -8.6111)  # ~15 m


def order(recs):
    return [r["id"] for r in recs]


def test_rain_pushes_indoor_places_above_open_air_ones():
    recs = nearby.recommend(HERE, RAIN, [PARK, MUSEUM], [], [], [])
    assert order(recs)[0] == "s1"
    assert "DYN-02" in recs[0]["rules"] and "indoor" in recs[0]["reason"].lower()


def test_good_weather_pushes_outdoor_places_up():
    recs = nearby.recommend(HERE, DRY, [MUSEUM, PARK], [], [], [])
    assert order(recs)[0] == "s2" and "DYN-03" in recs[0]["rules"]


def test_meal_times_choose_the_right_kind_of_place():
    cafe, resto = food("f1", "Bean", "cafe", 41.1498, -8.6110), food("f2", "Tasca", "restaurant", 41.1498, -8.6111)
    breakfast = nearby.recommend(HERE, {**DRY, "local_hour": 8}, [], [resto, cafe], [], [])
    lunch = nearby.recommend(HERE, {**DRY, "local_hour": 13}, [], [cafe, resto], [], [])
    assert order(breakfast)[0] == "f1" and "DYN-04" in breakfast[0]["rules"]
    assert order(lunch)[0] == "f2" and "DYN-05" in lunch[0]["rules"]


def test_evening_prefers_bars_only_when_you_like_nightlife():
    bar, resto = food("f3", "Pub", "pub", 41.1498, -8.6110), food("f4", "Cantina", "restaurant", 41.1498, -8.6110)
    plain = nearby.recommend(HERE, {**DRY, "local_hour": 20}, [], [bar, resto], [], [])
    night = nearby.recommend(HERE, {**DRY, "local_hour": 20}, [], [bar, resto], [], ["nightlife"])
    assert order(plain)[0] == "f4"
    assert order(night)[0] == "f3" and {"DYN-06", "DYN-07"} <= set(night[0]["rules"])


def test_planned_items_nearby_come_first_and_far_ones_are_ignored():
    planned = [{"name": "Livraria", "lat": 41.1470, "lng": -8.6150}, {"name": "Faraway", "lat": 41.5, "lng": -8.0}]
    recs = nearby.recommend(HERE, DRY, [MUSEUM], [], planned, [])
    assert recs[0]["kind"] == "plan" and recs[0]["title"] == "Livraria" and "DYN-01" in recs[0]["rules"]
    assert "Faraway" not in [r["title"] for r in recs]


def test_interests_boost_matching_sights():
    a = sight("a", "Old Square", "Historic square", 41.1497, -8.6110, tags=["old-town"])
    b = sight("b", "Plain Tower", "Tower", 41.1497, -8.6110)
    assert order(nearby.recommend(HERE, DRY, [b, a], [], [], ["old-town"]))[0] == "a"


def test_nearer_places_rank_higher_and_out_of_radius_places_are_dropped():
    near, far = sight("n", "Near", "Church", 41.1498, -8.6110), sight("f", "Far", "Church", 41.1590, -8.6110)  # ~1 km
    out = nearby.recommend(HERE, DRY, [far, near], [], [], [], radius_m=1500)
    assert order(out) == ["n", "f"] and all("DYN-08" in r["rules"] for r in out)
    assert order(nearby.recommend(HERE, DRY, [far, near], [], [], [], radius_m=300)) == ["n"]
    assert "min walk" in out[0]["reason"]


def test_results_are_capped_and_have_unique_ids():
    many = [sight(f"s{i}", f"Church {i}", "Church", 41.1497 + i * 0.0001, -8.6110) for i in range(20)]
    recs = nearby.recommend(HERE, DRY, many, [], [], [], limit=5)
    assert len(recs) <= 5 and len(set(order(recs))) == len(recs)


def test_every_rule_in_the_code_is_documented_in_the_feature_registry():
    text = (Path(__file__).resolve().parents[2] / "docs" / "FEATURES.md").read_text(encoding="utf-8")
    missing = [rule for rule in nearby.RULES if rule not in text]
    assert not missing, f"Add these dynamic rules to docs/FEATURES.md: {missing}"


def test_every_rule_that_fires_is_a_declared_rule():
    recs = nearby.recommend(HERE, RAIN, [MUSEUM, PARK], [food("f", "X", "cafe", 41.1498, -8.6110)],
                            [{"name": "P", "lat": 41.1499, "lng": -8.6112}], ["old-town", "nightlife"])
    fired = {rule for r in recs for rule in r["rules"]}
    assert fired and fired <= set(nearby.RULES)


def test_runtime_log_records_rules_and_city_but_never_coordinates(tmp_path):
    log = tmp_path / "dynamic-features.md"
    recs = nearby.recommend(HERE, RAIN, [MUSEUM], [], [], [])
    nearby.log_event("Porto", recs, RAIN, path=log)
    nearby.log_event("Porto", recs, DRY, path=log)
    text = log.read_text(encoding="utf-8")
    assert text.startswith("# Dynamic feature log") and text.count("| Porto |") == 2
    assert "DYN-02" in text and "rain" in text
    assert "41.14" not in text and "8.61" not in text  # no position leaks into the log


def test_nearest_city_names_the_catalog_city_or_says_outside():
    assert nearby.nearest_city(41.15, -8.61) == "Porto"
    assert nearby.nearest_city(-30.0, 0.0) == "(outside the catalog)"


# ---------------------------------------------------------------- API

def test_nearby_endpoint_validates_input_and_reports_offline(client):
    assert client.post("/api/nearby", json={"lat": 999, "lng": 0}).status_code == 422
    assert client.post("/api/nearby", json={"lat": 41.1, "lng": -8.6, "radius_m": 10}).status_code == 422
    ok = client.post("/api/nearby", json={"lat": 41.1, "lng": -8.6})
    assert ok.status_code == 200 and ok.json()["recommendations"] == [] and "Offline" in ok.json()["notes"][0]


def test_nearby_endpoint_passes_position_interests_and_plan_to_the_engine(client, monkeypatch):
    from app import config, main

    seen = {}

    def fake_run(lat, lng, interests, planned, radius_m):
        seen.update(lat=lat, lng=lng, interests=interests, planned=planned, radius=radius_m)
        return {"context": {"city": "Porto"}, "recommendations": [{"id": "x"}], "notes": [], "generated_at": "t"}

    monkeypatch.setattr(config, "offline", lambda: False)
    monkeypatch.setattr(main.config, "offline", lambda: False)
    monkeypatch.setattr(main.nearby, "run", fake_run)
    body = {"lat": 41.15, "lng": -8.61, "interests": ["nightlife"], "planned": [{"name": "Livraria", "lat": 41.14, "lng": -8.61}]}
    res = client.post("/api/nearby", json=body)
    assert res.status_code == 200 and res.json()["recommendations"] == [{"id": "x"}]
    assert seen["interests"] == ["nightlife"] and seen["planned"][0]["name"] == "Livraria" and seen["radius"] == 1500
