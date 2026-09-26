"""The trip builder must follow the person's words, not the form. The model is faked, so no network or credits."""
from datetime import date

import pytest

from app.live import catalog, llm
from app.live.osm import route_stop_names, route_waypoints

TODAY = date(2026, 9, 21)


def fake_model(monkeypatch, trip=None, profile=None):
    monkeypatch.setattr(llm, "_chat", lambda *a, **k: {"trip": trip or {}, "profile": profile or {}})


def cities(result):
    return sorted(c["city"] for c in result.get("destination_choices", []))


def test_text_scan_finds_cities_and_countries_ignoring_accents_and_case():
    f = catalog.find_in_text("flights from london to KRAKÓW, then maybe portugal")
    assert sorted(c["city"] for c in f["cities"]) == ["Krakow", "London"] and f["countries"] == ["Portugal"]
    assert catalog.find_in_text("the UK in winter")["countries"] == ["United Kingdom"]


def test_ordinary_words_that_are_also_city_names_are_not_matched():
    assert catalog.find_in_text("a nice male traveller, split the bill")["cities"] == []


def test_a_named_country_with_several_cities_asks_instead_of_using_the_form(monkeypatch):
    fake_model(monkeypatch, trip={"destination": None, "place_mentioned": "Italy"})
    result = llm.build_trip("a week in Italy with wine and museums", today=TODAY)
    assert "destination" not in result
    assert cities(result) == ["Florence", "Milan", "Naples", "Rome", "Venice"]
    assert result["place_mentioned"] == "Italy"


def test_a_named_city_is_used_even_if_the_model_returned_nothing(monkeypatch):
    fake_model(monkeypatch, trip={"destination": None})
    result = llm.build_trip("Four days in Porto in December for two", today=TODAY)
    assert result["destination"] == "OPO" and "Porto" in " ".join(result["assumptions"])


def test_the_origin_city_is_never_mistaken_for_the_destination(monkeypatch):
    fake_model(monkeypatch, trip={"origin": "LON", "destination": None})
    result = llm.build_trip("from London to somewhere in Portugal", today=TODAY)
    assert "destination" not in result and cities(result) == ["Lisbon", "Porto"]


def test_several_named_cities_become_an_ordered_route(monkeypatch):
    fake_model(monkeypatch, trip={"destination": None})
    result = llm.build_trip("10 days across Paris, Rome and Athens", today=TODAY)
    assert result["destination"] == "PAR"
    assert result["destinations"] == ["PAR", "ROM", "ATH"]
    assert "Paris → Rome → Athens" in " ".join(result["assumptions"])


def test_route_area_text_splits_into_waypoints():
    assert route_stop_names("Adelaide to Coober Pedy to Alice Springs") == ["Adelaide", "Coober Pedy", "Alice Springs"]
    assert route_stop_names("Day 4 route: Lisbon via Sintra, then Cascais") == ["Lisbon", "Sintra", "Cascais"]
    assert route_stop_names("build route from geneva to monaco") == ["geneva", "monaco"]
    assert route_stop_names("build me a route from paris to geneva with history sites nature good food please keep it not more than 5 km from straight line route") == ["paris", "geneva"]


def test_route_waypoints_keep_monaco_on_the_riviera():
    stops = route_waypoints("build route from geneva to monaco", "France")
    assert [s["name"] for s in stops] == ["Geneva", "Monaco"]
    assert stops[1]["lat"] == 43.7384
    assert stops[1]["lng"] == 7.4246


def test_a_country_with_one_catalog_city_is_used_directly(monkeypatch):
    fake_model(monkeypatch, trip={"destination": None})
    assert llm.build_trip("a long weekend in Austria", today=TODAY)["destination"] == "VIE"


def test_the_models_own_choice_is_respected(monkeypatch):
    fake_model(monkeypatch, trip={"destination": "ROM", "assumptions": ["You said Italy, so I chose Rome."]})
    result = llm.build_trip("a week in Italy", today=TODAY)
    assert result["destination"] == "ROM" and "destination_choices" not in result


def test_a_country_we_do_not_cover_is_not_swapped_for_another_place(monkeypatch):
    """The real model once answered 'Egypt in winter' with Cancun. A specific place we lack must be reported, not replaced."""
    fake_model(monkeypatch, trip={"destination": "CUN", "place_mentioned": "Egypt", "place_kind": "country",
                                  "assumptions": ["The traveler likely meant Cancun"]})
    result = llm.build_trip("Egypt in winter, pyramids and diving", today=TODAY)
    assert result["destination"] == "Egypt" and result["dynamic_places"] == ["Egypt"]
    assert result["place_mentioned"] == "Egypt" and "place_kind" not in result


def test_a_vague_wish_may_still_get_a_suggestion_and_says_so(monkeypatch):
    fake_model(monkeypatch, trip={"destination": "CUN", "place_mentioned": "somewhere warm", "place_kind": "vague",
                                  "assumptions": ["Selected Cancun for a warm beach holiday"]})
    result = llm.build_trip("beach holiday somewhere warm", today=TODAY)
    assert result["destination"] == "CUN" and result["assumptions"]


def test_a_model_pick_that_contradicts_the_named_place_loses_to_the_words(monkeypatch):
    fake_model(monkeypatch, trip={"destination": "NAP", "place_kind": "city"})  # the old form default, not what was asked
    assert llm.build_trip("a weekend in Lisbon", today=TODAY)["destination"] == "LIS"
    fake_model(monkeypatch, trip={"destination": "PAR", "place_kind": "country"})
    result = llm.build_trip("a week in Italy", today=TODAY)
    assert "destination" not in result and len(result["destination_choices"]) == 5


def test_a_place_we_do_not_cover_is_reported_not_replaced(monkeypatch):
    fake_model(monkeypatch, trip={"destination": None, "place_mentioned": "Egypt"})
    result = llm.build_trip("two weeks in Egypt", today=TODAY)
    assert result["destination"] == "Egypt" and result["dynamic_places"] == ["Egypt"]


def test_unsupported_prompt_places_are_not_replaced_with_los_angeles(monkeypatch):
    fake_model(monkeypatch, trip={"destination": "LAX", "place_mentioned": "Hawaii, New Zealand and Australia", "place_kind": "region"})
    result = llm.build_trip("I want Hawaii, New Zealand and Australia", today=TODAY)
    assert result["destination"] == "Hawaii"
    assert result["destinations"] == ["Hawaii", "New Zealand", "Australia"]
    assert result["dynamic_places"] == ["Hawaii", "New Zealand"]
    assert "destination_choices" not in result


def test_invalid_model_destinations_are_dropped_then_resolved_from_the_text(monkeypatch):
    fake_model(monkeypatch, trip={"destination": "XXX"})
    assert llm.build_trip("weekend in Lisbon", today=TODAY)["destination"] == "LIS"


@pytest.mark.parametrize("text", ["", "some sunshine please"])
def test_nothing_named_means_no_destination_and_no_choices(monkeypatch, text):
    fake_model(monkeypatch, trip={"destination": None})
    result = llm.build_trip(text, today=TODAY)
    assert "destination" not in result and "destination_choices" not in result
