"""Tests for the live-data layer. Everything here is pure or uses fixtures: no network, no API keys."""
import json
from datetime import date

import pytest

from app.live import amadeus, catalog, climate, llm, osm, places, pricing, travel
from app.ranking.combine import rank_and_combine
from app.ranking.score import score_hotels

# ---------------------------------------------------------------- catalog

def test_catalog_has_exactly_109_destinations_across_four_regions():
    assert len(catalog.DESTINATIONS) == 109
    assert len({d["code"] for d in catalog.DESTINATIONS}) == 109
    by_region = {}
    for d in catalog.DESTINATIONS:
        by_region[d["region"]] = by_region.get(d["region"], 0) + 1
    assert by_region == {"Europe": 41, "Americas": 30, "Asia": 30, "Oceania": 8}


def test_catalog_entries_are_well_formed():
    for d in catalog.DESTINATIONS:
        assert len(d["code"]) == 3 and d["code"].isupper(), d["code"]
        assert -90 <= d["lat"] <= 90 and -180 <= d["lng"] <= 180, d["code"]
        assert d["cost"] in (1, 2, 3, 4), d["code"]
        assert d["city"] and d["country"] and d["wiki"]


def test_resolve_by_code_and_city_name_case_insensitively():
    assert catalog.resolve("nap")["city"] == "Naples"
    assert catalog.resolve("Tokyo")["code"] == "TYO"
    assert catalog.resolve("Atlantis") is None and catalog.resolve("") is None


def test_showcase_and_curated_cities_are_in_the_catalog():
    for code in ("NAP", "LIS", "TYO", "DXB", "BCN", "ROM", "PAR", "ATH", "NYC", "TLV"):
        assert code in catalog.BY_CODE


# ---------------------------------------------------------------- climate

def test_suitability_rewards_mild_dry_weather_and_punishes_extremes():
    assert climate.suitability(24, 0.05) == 5
    assert climate.suitability(0, 0.1) <= 2
    assert climate.suitability(42, 0.0) <= 3
    assert climate.suitability(24, 0.05) > climate.suitability(24, 0.9)  # rain lowers the score
    assert all(1 <= climate.suitability(t, r) <= 5 for t in range(-20, 50, 5) for r in (0, 0.3, 0.7, 1))


def test_aggregate_turns_daily_data_into_twelve_monthly_scores():
    days = [f"2021-{m:02d}-{d:02d}" for m in range(1, 13) for d in range(1, 29)]
    daily = {
        "time": days,
        "temperature_2m_max": [(30 if d[5:7] in ("07", "08") else 12) for d in days],
        "temperature_2m_min": [10] * len(days),
        "precipitation_sum": [0.0] * len(days),
    }
    out = climate._aggregate(daily)
    assert len(out["scores"]) == 12 and len(out["months"]) == 12
    assert out["months"][6]["tmax"] == 30 and out["months"][0]["tmax"] == 12
    assert out["scores"][6] > out["scores"][0] or out["scores"][6] >= 4


# ---------------------------------------------------------------- pricing

def test_hotel_estimate_scales_with_stars_and_city_price_level_and_is_deterministic():
    cheap, dear = catalog.BY_CODE["BKK"], catalog.BY_CODE["ZRH"]
    three = pricing.hotel_night_estimate(dear, 3, 3, "Hotel X")
    five = pricing.hotel_night_estimate(dear, 5, 3, "Hotel X")
    assert five > three
    assert pricing.hotel_night_estimate(dear, 3, 3, "Hotel X") > pricing.hotel_night_estimate(cheap, 3, 3, "Hotel X")
    assert pricing.hotel_night_estimate(dear, 3, 3, "Hotel X") == three  # same input, same output


def test_flight_estimates_grow_with_distance_and_are_labelled_estimates():
    lon = catalog.BY_CODE["LON"]
    near = pricing.flight_options_estimate(lon, catalog.BY_CODE["PAR"], "2026-11-10", "2026-11-17", 2)
    far = pricing.flight_options_estimate(lon, catalog.BY_CODE["TYO"], "2026-11-10", "2026-11-17", 2)
    assert min(o["price_per_traveler"] for o in far) > min(o["price_per_traveler"] for o in near)
    for o in near + far:
        assert o["price_source"] == "estimate" and o["total_price"] == o["price_per_traveler"] * 2
    # beyond nonstop range there are no direct options
    assert all(o["stops"] > 0 for o in pricing.flight_options_estimate(catalog.BY_CODE["SCL"], catalog.BY_CODE["TYO"], "2026-11-10", "2026-11-17", 1))


# ---------------------------------------------------------------- OpenStreetMap

FAKE_AREA = {
    "hotels": [
        {"type": "node", "id": 1, "pt": (41.150, -8.610), "tags": {"name": "Grand Central", "tourism": "hotel", "stars": "5", "website": "https://x.example", "internet_access": "wlan"}},
        {"type": "node", "id": 2, "pt": (41.152, -8.611), "tags": {"name": "Plain Inn", "tourism": "guest_house"}},
        {"type": "node", "id": 3, "pt": (41.150, -8.610), "tags": {"name": "Grand Central", "tourism": "hotel"}},  # duplicate name
    ],
    "beaches": [(41.15, -8.62)],
    "bars": [(41.1501, -8.6101)] * 8,
    "restaurants": [{"name": "Rio", "cuisine": "portuguese", "pt": (41.1502, -8.6102), "website": None},
                    {"name": "Far Away", "cuisine": "pizza", "pt": (41.30, -8.40), "website": None}],
    "source": "OpenStreetMap (test)",
}


@pytest.fixture
def fake_osm(monkeypatch):
    monkeypatch.setattr(osm, "area", lambda dest: FAKE_AREA)


def test_real_hotels_are_deduplicated_ranked_by_notability_and_carry_real_signals(fake_osm):
    hotels = osm.real_hotels(catalog.BY_CODE["OPO"], limit=8)
    assert [h["name"] for h in hotels] == ["Grand Central", "Plain Inn"]
    top = hotels[0]
    assert top["stars"] == 5 and "Wi-Fi" in top["amenities"] and top["website"] == "https://x.example"
    assert top["signals"]["bars_300m"] == 8 and "nightlife" in top["tags"]
    assert "price_per_night" not in top  # OSM has no prices; none are invented


def test_interest_tags_follow_the_signals():
    assert "beachfront" in osm.interest_tags(2, 0, 0, 300, {})
    assert "nightlife" in osm.interest_tags(2, 9, 0, None, {})
    assert "quiet" in osm.interest_tags(2.5, 1, 0, None, {})
    assert "old-town" in osm.interest_tags(0.5, 0, 0, None, {})
    assert "nightlife" not in osm.interest_tags(2, None, 0, None, {})  # unknown signal is not guessed


def test_nearby_restaurants_are_real_sorted_and_have_no_invented_prices(fake_osm):
    found = osm.nearby_restaurants(catalog.BY_CODE["OPO"], 41.1500, -8.6100)
    assert [v["name"] for v in found] == ["Rio"]  # the far one is outside the radius
    assert found[0]["price"] is None and found[0]["deal"] is None and found[0]["blurb"] == "Portuguese"


def test_star_parsing():
    assert osm._stars({"stars": "4"}) == 4 and osm._stars({"stars": "3S"}) == 3
    assert osm._stars({}) is None and osm._stars({"stars": "0"}) is None


# ---------------------------------------------------------------- Wikipedia

def test_sight_scoring_prefers_viewed_attractions_and_drops_junk():
    good = {"title": "Old Bridge", "description": "Bridge in Porto", "thumbnail": {"source": "x"}, "pageimage": "Bridge.jpg", "pageviews": {"d1": 5000, "d2": None}}
    quiet = {**good, "title": "Old Chapel", "description": "Chapel", "pageviews": {"d1": 5}}
    assert places._score(good) > places._score(quiet) > 0
    assert places._score({**good, "description": "Street circuit in Portugal"}) == -1
    assert places._score({**good, "pageimage": "Route_map.svg"}) == -1
    assert places._score({**good, "thumbnail": None}) == -1


def test_credits_keep_only_reuse_with_credit_licences(monkeypatch):
    def fake_api(params):
        def page(title, lic):
            return {"title": f"File:{title}", "imageinfo": [{"descriptionurl": "u", "extmetadata": {
                "LicenseShortName": {"value": lic}, "Artist": {"value": "<a>Ann</a>"}}}]}
        return {"query": {"pages": [page("A.jpg", "CC BY-SA 4.0"), page("B.jpg", "CC BY-NC 2.0"), page("C.jpg", "Public domain")]}}
    monkeypatch.setattr(places, "_api", fake_api)
    out = places.credits_for(["A.jpg", "B.jpg", "C.jpg"])
    assert set(out) == {"A.jpg", "C.jpg"} and out["A.jpg"]["author"] == "Ann"


def test_place_classification_uses_word_boundaries():
    assert "beachfront" in places.classify("A sandy beach on the coast")
    assert "beachfront" not in places.classify("Lisbon Racecourse and Turnbay")


# ---------------------------------------------------------------- Amadeus parsing (sample payloads)

def test_amadeus_duration_and_flight_parsing():
    assert amadeus.parse_duration("PT7H35M") == 455 and amadeus.parse_duration("PT45M") == 45 and amadeus.parse_duration("") == 0
    payload = {"dictionaries": {"carriers": {"TP": "TAP Air Portugal"}}, "data": [{
        "id": "1", "validatingAirlineCodes": ["TP"], "price": {"grandTotal": "412.50", "currency": "GBP"},
        "itineraries": [{"duration": "PT2H55M", "segments": [{"carrierCode": "TP", "departure": {"at": "2026-11-10T07:25:00"}}]}],
    }]}
    (o,) = amadeus.parse_flight_offers(payload, "LON", "OPO", "2026-11-10", "2026-11-17", 2)
    assert o["airline"] == "TAP Air Portugal" and o["stops"] == 0 and o["depart_time"] == "07:25"
    assert o["price_per_traveler"] == 206 and o["total_price"] == 412 and o["price_source"] == "amadeus"


def test_amadeus_hotel_offer_parsing_skips_incomplete_entries():
    payload = {"data": [
        {"hotel": {"hotelId": "A1", "name": "SOME HOTEL", "latitude": 41.1, "longitude": -8.6, "rating": "4"},
         "offers": [{"price": {"total": "700.00", "currency": "GBP"}}]},
        {"hotel": {"hotelId": "B2", "name": "NO OFFER", "latitude": 41.1, "longitude": -8.6}, "offers": []},
    ]}
    (h,) = amadeus.parse_hotel_offers(payload, nights=7)
    assert h["name"] == "Some Hotel" and h["price_per_night"] == 100 and h["rating"] == 4.0


# ---------------------------------------------------------------- OpenAI guard rails

def test_request_normalisation_drops_anything_not_trustworthy():
    raw = {"origin": "LON", "destination": "Atlantis", "start_date": "2026-12-01", "end_date": "2026-12-08",
           "budget": -5, "travelers": 99, "interests": ["nightlife", "skydiving"], "assumptions": ["Assumed GBP"]}
    out = llm.normalize_request(raw, date(2026, 9, 1))
    assert out["origin"] == "LON" and "destination" not in out
    assert out["start_date"] == "2026-12-01" and "budget" not in out and "travelers" not in out
    assert out["interests"] == ["nightlife"] and out["assumptions"] == ["Assumed GBP"]


def test_request_normalisation_derives_end_date_from_nights_and_rejects_past_dates():
    ok = llm.normalize_request({"destination": "opo", "start_date": "2026-10-01", "nights": 7}, date(2026, 9, 1))
    assert ok["destination"] == "OPO" and ok["end_date"] == "2026-10-08"
    past = llm.normalize_request({"start_date": "2020-01-01", "end_date": "2020-01-08"}, date(2026, 9, 1))
    assert "start_date" not in past


def test_grounding_check_rejects_invented_numbers():
    facts = {"total": 1191, "nights": 7, "hotel": "Eurostars", "price_per_night": 133}
    assert llm.is_grounded("A 7 night trip for £1,191 at £133 a night.", facts)
    assert not llm.is_grounded("A 7 night trip for £1,050.", facts)  # 1050 is not in the facts
    assert llm.is_grounded("A lovely trip with no numbers at all.", facts)


def test_summarize_returns_grounded_text_only(monkeypatch):
    facts = {"total": 800, "nights": 5}
    monkeypatch.setattr(llm, "_chat", lambda *a, **k: {"summary": "Five nights for £800 in total."})
    assert llm.summarize(facts) == "Five nights for £800 in total."  # words are fine; only digits are checked
    monkeypatch.setattr(llm, "_chat", lambda *a, **k: {"summary": "5 nights for £800."})
    assert llm.summarize(facts) == "5 nights for £800."
    monkeypatch.setattr(llm, "_chat", lambda *a, **k: {"summary": "5 nights for £999."})
    assert llm.summarize(facts) is None


# ---------------------------------------------------------------- live search assembly

def test_live_flight_search_falls_back_to_labelled_estimates_without_amadeus():
    res = travel.search_flights("LON", "NAP", "2026-11-10", "2026-11-17", 2)
    assert res["source"] == "estimate" and res["options"]
    assert travel.search_flights("LON", "Atlantis", "2026-11-10", "2026-11-17", 2) is None  # unknown -> demo
    assert travel.search_flights("LON", "LON", "2026-11-10", "2026-11-17", 2) is None


def test_live_hotel_search_prices_real_hotels_with_estimates(fake_osm, monkeypatch):
    monkeypatch.setattr(climate, "monthly_climate", lambda dest: {"scores": [3] * 12, "months": [], "source": "t"})
    res = travel.search_hotels("OPO", "2026-11-10", "2026-11-17", 2)
    assert res["source"] == "estimate" and "estimates" in res["detail"]
    for h in res["options"]:
        assert h["price_source"] == "estimate" and h["rating"] is None and h["price_per_night"] > 0


# ---------------------------------------------------------------- ranking with stars instead of guest ratings

def test_ranking_and_copy_handle_star_class_without_claiming_guest_ratings():
    flights = [{"id": "F", "airline": "Typical direct fare", "price_per_traveler": 100, "total_price": 200,
                "duration_minutes": 150, "stops": 0, "price_source": "estimate"}]
    hotels = [
        {"id": "H1", "name": "Five Star", "price_per_night": 120, "rating": None, "stars": 5, "tags": ["nightlife"], "distance_to_center_km": 1.0},
        {"id": "H2", "name": "Two Star", "price_per_night": 60, "rating": None, "stars": 2, "tags": [], "distance_to_center_km": 4.0},
        {"id": "H3", "name": "Unrated", "price_per_night": 80, "rating": None, "stars": None, "tags": [], "distance_to_center_km": 2.0},
    ]
    assert score_hotels(hotels, ["nightlife"])[0]["hotel"]["id"] == "H1"
    result = rank_and_combine(flights, hotels, nights=5, budget=2000, interests=["nightlife"])
    text = " ".join(result["chosen"]["pros"] + result["chosen"]["cons"] + result["rationale"])
    assert "5-star" in text and "out of 5" not in text
    assert "typical direct fare" in " ".join(result["rationale"])
    assert json.dumps(result["alternatives"][0]["pros"] + result["alternatives"][0]["cons"])  # comparisons don't crash on None ratings


# ---------------------------------------------------------------- configuration and OpenAI request shape

def test_env_file_loading_ignores_comments_and_never_overrides_real_variables(tmp_path, monkeypatch):
    from app import config

    env = tmp_path / ".env"
    env.write_text('# comment\nOPENAI_API_KEY="sk-test"\nAMADEUS_CLIENT_ID = abc\nMALFORMED\nWAYFINDER_TEST_KEEP=from-file\n', encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AMADEUS_CLIENT_ID", raising=False)
    monkeypatch.setenv("WAYFINDER_TEST_KEEP", "from-environment")
    config.load_env_file(env)
    import os

    assert os.environ["OPENAI_API_KEY"] == "sk-test" and os.environ["AMADEUS_CLIENT_ID"] == "abc"
    assert os.environ["WAYFINDER_TEST_KEEP"] == "from-environment"
    monkeypatch.delenv("OPENAI_API_KEY"); monkeypatch.delenv("AMADEUS_CLIENT_ID")


def test_offline_mode_disables_openai_and_amadeus_even_when_keys_are_present(monkeypatch):
    from app import config

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("AMADEUS_CLIENT_ID", "id")
    monkeypatch.setenv("AMADEUS_CLIENT_SECRET", "secret")
    assert config.offline() and config.openai_key() is None and config.amadeus_credentials() is None
    monkeypatch.setenv("WAYFINDER_OFFLINE", "0")
    assert config.openai_key() == "sk-test" and config.amadeus_credentials() == ("id", "secret")
    monkeypatch.setenv("WAYFINDER_OFFLINE", "1")


def test_openai_request_uses_bearer_key_json_mode_and_the_configured_model(monkeypatch):
    monkeypatch.setenv("WAYFINDER_OFFLINE", "0")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "my-model")
    sent = {}

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": '{"summary": "ok"}'}}]}

    class FakeClient:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None):
            sent.update(url=url, headers=headers, body=json)
            return FakeResponse()

    monkeypatch.setattr(llm, "client", lambda timeout=30: FakeClient())
    try:
        assert llm._chat("system text", "user text") == {"summary": "ok"}
    finally:
        monkeypatch.setenv("WAYFINDER_OFFLINE", "1")
    assert sent["url"] == "https://api.openai.com/v1/chat/completions"
    assert sent["headers"]["Authorization"] == "Bearer sk-test"
    assert sent["body"]["model"] == "my-model" and sent["body"]["response_format"] == {"type": "json_object"}
    assert [m["role"] for m in sent["body"]["messages"]] == ["system", "user"]


def test_parse_prompt_lists_every_catalog_code_so_the_model_cannot_invent_destinations(monkeypatch):
    captured = {}
    monkeypatch.setattr(llm, "_chat", lambda system, user, max_tokens=600: captured.update(system=system, user=user) or {"destination": "LIS"})
    out = llm.parse_trip_request("a week in Lisbon", date(2026, 9, 1))
    assert out["destination"] == "LIS"
    assert all(f"{d['code']}={d['city']}" in captured["system"] for d in catalog.DESTINATIONS)
    assert "2026-09-01" in captured["system"]


def test_normalisation_survives_a_string_where_a_list_was_requested():
    out = llm.normalize_request({"destination": "OPO", "interests": "nightlife", "assumptions": "Assumed GBP"}, date(2026, 9, 1))
    assert out["assumptions"] == ["Assumed GBP"] and out["interests"] == ["nightlife"]
    assert llm.normalize_request({"assumptions": None, "interests": None}, date(2026, 9, 1))["assumptions"] == []


def test_summary_retries_once_telling_the_model_which_numbers_are_allowed(monkeypatch):
    calls = []

    def fake_chat(system, user, max_tokens=600):
        calls.append(system)
        return {"summary": "Around 9 hours in total." if len(calls) == 1 else "A 5 night trip for £800."}

    monkeypatch.setattr(llm, "_chat", fake_chat)
    assert llm.summarize({"total": 800, "nights": 5}) == "A 5 night trip for £800."
    assert len(calls) == 2 and "Only these numbers may appear: 5, 800" in calls[1] and "9" in calls[1]
    monkeypatch.setattr(llm, "_chat", lambda *a, **k: {"summary": "It costs £1,234."})
    assert llm.summarize({"total": 800}) is None  # still invented after the retry, so nothing is shown


def test_number_matching_ignores_formatting_differences():
    facts = {"dates": "2 December 2026 to 5 December 2026", "budget": 900.0, "iso": "2026-12-05"}
    assert llm.is_grounded("Arrive on 5 December with a budget of £900.", facts)
    assert llm.is_grounded("That is 05 December.", facts)
    assert not llm.is_grounded("That is 6 December.", facts)


# ---------------------------------------------------------------- trip builder: profile, photo, place types, packages

def test_profile_normalisation_keeps_only_known_keys_and_bounds_text():
    raw = {"summary": "x" * 500, "keywords": ["Wine", "  ", "a" * 60] + [f"k{i}" for i in range(20)],
           "interests": ["nightlife", "skydiving"], "place_types": ["museum", "pub", "casino"],
           "vibe": "cultural", "pace": "sprint", "budget_style": "premium"}
    p = llm.normalize_profile(raw)
    assert len(p["summary"]) == 300 and p["keywords"][0] == "wine" and len(p["keywords"]) == 8 and len(p["keywords"][1]) == 30
    assert p["interests"] == ["nightlife"] and p["place_types"] == ["museum", "pub"]
    assert p["vibe"] == "cultural" and p["pace"] is None and p["budget_style"] == "premium"
    assert llm.normalize_profile(None)["keywords"] == []


def test_image_validation_accepts_small_image_data_urls_only():
    ok = "data:image/jpeg;base64,/9j/4AAQSkZJRg=="
    assert llm.valid_image(ok) and llm.valid_image("data:image/png;base64,iVBORw0KGgo=")
    assert not llm.valid_image(None) and not llm.valid_image("http://evil.example/x.jpg")
    assert not llm.valid_image("data:text/html;base64,PGh0bWw+") and not llm.valid_image("data:image/svg+xml;base64,PHN2Zz4=")
    assert not llm.valid_image("data:image/jpeg;base64," + "A" * llm.MAX_IMAGE_CHARS)


def test_build_trip_sends_the_photo_only_when_valid_and_returns_trip_plus_profile(monkeypatch):
    seen = {}

    def fake_chat(system, user, max_tokens=600, image=None):
        seen.update(system=system, image=image)
        return {"trip": {"destination": "opo", "start_date": "2026-12-02", "nights": 3, "assumptions": ["Guessed 3 nights"]},
                "profile": {"keywords": ["wine"], "place_types": ["museum", "pub"], "vibe": "cultural"}}

    monkeypatch.setattr(llm, "_chat", fake_chat)
    img = "data:image/jpeg;base64,/9j/4AAQ"
    out = llm.build_trip("wine and museums", img, date(2026, 9, 1))
    assert seen["image"] == img and "Never identify or describe any person" in seen["system"]
    assert out["destination"] == "OPO" and out["end_date"] == "2026-12-05"
    assert out["profile"]["place_types"] == ["museum", "pub"] and out["assumptions"] == ["Guessed 3 nights"]
    llm.build_trip("wine", "not-an-image", date(2026, 9, 1))
    assert seen["image"] is None  # an invalid image is never forwarded


def test_openai_vision_message_shape(monkeypatch):
    monkeypatch.setenv("WAYFINDER_OFFLINE", "0")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    sent = {}

    class R:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": "{}"}}]}

    class C:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None):
            sent.update(body=json)
            return R()

    monkeypatch.setattr(llm, "client", lambda timeout=30: C())
    try:
        llm._chat("sys", "hello", 50, image="data:image/jpeg;base64,AAAA")
    finally:
        monkeypatch.setenv("WAYFINDER_OFFLINE", "1")
    content = sent["body"]["messages"][1]["content"]
    assert content[0] == {"type": "text", "text": "hello"} and content[1]["image_url"]["url"].startswith("data:image/jpeg")


def test_places_of_type_groups_ranks_notable_first_and_reports_empty_types(monkeypatch):
    def rec(name, kind, dist, notable=False, site=None):
        return {"id": name, "type": kind, "name": name, "lat": 1, "lng": 1, "distance_to_center_km": dist,
                "website": site, "opening_hours": None, "wikipedia": None, "osm_url": "u", "notable": notable}

    found = [rec("Far Museum", "museum", 3.0, notable=True), rec("Near Museum", "museum", 0.2), rec("Near Museum", "museum", 0.2),
             rec("Pub A", "pub", 0.5), rec("Pub B", "pub", 0.4, site="https://b.example")]
    monkeypatch.setattr(osm, "cached", lambda key, ttl, fetch: found)
    out = osm.places_of_type(catalog.BY_CODE["OPO"], ["museum", "pub", "market", "casino", "museum"])
    assert list(out) == ["museum", "pub", "market"]  # unknown types dropped, duplicates ignored
    assert [p["name"] for p in out["museum"]] == ["Far Museum", "Near Museum"]  # notable first, duplicate removed
    assert out["pub"][0]["name"] == "Pub B" and out["market"] == []
    assert osm.places_of_type(catalog.BY_CODE["OPO"], ["casino"]) == {}


def test_price_packages_label_the_cheapest_best_and_comfort_options():
    from app.nodes import _packages

    def combo(fid, hid, total, stars):
        return {"flight": {"id": fid, "price_source": "estimate"}, "hotel": {"id": hid, "stars": stars, "rating": None, "price_source": "estimate"}, "total_cost": total}

    cheap, best, plush = combo("f1", "h1", 500, 2), combo("f1", "h2", 700, 3), combo("f2", "h3", 1200, 5)
    packages = _packages([cheap, best, plush], chosen=best)
    assert [p["labels"] for p in packages] == [["Cheapest"], ["Best match"], ["Comfort"]]
    assert [p["vs_best"] for p in packages] == [-200, 0, 500] and packages[0]["price_sources"]["hotel"] == "estimate"
    merged = _packages([best, plush], chosen=best)  # best is also the cheapest: one card, two labels
    assert merged[0]["labels"] == ["Cheapest", "Best match"] and len(merged) == 2
