from datetime import date

from app.mcp_tools.guides_data import GUIDES, _month_windows, assess_timing, build_guide
from app.ranking.combine import rank_and_combine

FLIGHTS = [
    {"id": "F1", "airline": "A", "price_per_traveler": 300, "total_price": 600, "duration_minutes": 180, "stops": 0},
    {"id": "F2", "airline": "B", "price_per_traveler": 150, "total_price": 300, "duration_minutes": 300, "stops": 1},
    {"id": "F3", "airline": "C", "price_per_traveler": 100, "total_price": 200, "duration_minutes": 600, "stops": 2},
]
HOTELS = [
    {"id": "H1", "name": "X", "price_per_night": 100, "rating": 4.5, "tags": ["beachfront", "spa"], "distance_to_center_km": 1.5},
    {"id": "H2", "name": "Y", "price_per_night": 200, "rating": 4.9, "tags": ["beachfront", "nightlife"], "distance_to_center_km": 6.0},
    {"id": "H3", "name": "Z", "price_per_night": 60, "rating": 3.5, "tags": ["quiet"], "distance_to_center_km": 3.0},
]


def test_month_windows_merge_runs_and_wrap_year_end():
    assert _month_windows([5, 6, 9, 10]) == "May-Jun, Sep-Oct"
    assert _month_windows([11, 12, 1, 2, 3]) == "Nov-Mar"
    assert _month_windows(list(range(1, 13))) == "Year-round"
    assert _month_windows([]) == ""


def test_timing_ideal_month_has_no_suggestion():
    timing = assess_timing(GUIDES["NAP"]["months"], date(2026, 9, 10), date(2026, 9, 20))
    assert timing["verdict"] == "Ideal"
    assert timing["suggestion"] is None


def test_timing_off_season_suggests_better_window():
    timing = assess_timing(GUIDES["DXB"]["months"], date(2026, 7, 1), date(2026, 7, 8))
    assert timing["verdict"] == "Off-season"
    assert "Nov-Mar" in timing["suggestion"]


def test_timing_averages_across_month_boundary():
    timing = assess_timing(GUIDES["TYO"]["months"], date(2026, 12, 28), date(2027, 1, 5))
    assert timing["trip_months"] == [12, 1]
    assert timing["verdict"] == "Fair"


def test_guide_ranks_interest_matches_first_and_handles_unknown_destination():
    guide = build_guide("nap", "2026-09-10", "2026-09-20", ["nightlife"])
    assert guide["places"][0]["matches"] == ["nightlife"]
    assert build_guide("XXX", "2026-09-10", "2026-09-20") == {"found": False, "destination": "XXX"}


def test_every_guide_is_well_formed():
    for code, g in GUIDES.items():
        assert len(g["months"]) == 12 and all(1 <= m <= 5 for m in g["months"]), code
        assert g["places"] and g["adventures"] and g["tips"], code


def test_chosen_pick_gets_pros_and_cons_grounded_in_the_numbers():
    result = rank_and_combine(FLIGHTS, HOTELS, nights=5, budget=2000, interests=["beachfront", "nightlife"])
    chosen = result["chosen"]
    assert chosen["pros"] and chosen["cons"]
    assert any("under your budget" in p for p in chosen["pros"])
    assert any("Does not cover: nightlife" in c for c in chosen["cons"])


def test_over_budget_is_called_out_as_a_con():
    result = rank_and_combine(FLIGHTS, HOTELS, nights=5, budget=100, interests=[])
    assert any("over your budget" in c for c in result["chosen"]["cons"])


def test_alternatives_are_compared_to_the_best_match():
    result = rank_and_combine(FLIGHTS, HOTELS, nights=5, budget=2000, interests=["beachfront", "nightlife"])
    chosen = result["chosen"]
    for alt in result["alternatives"]:
        assert alt["pros"] and alt["cons"]
        diff = alt["total_cost"] - chosen["total_cost"]
        text = " ".join(alt["pros"] + alt["cons"])
        if diff > 0:
            assert f"£{diff:.0f} more expensive" in text
        elif diff < 0:
            assert f"£{-diff:.0f} cheaper" in text


def test_rich_content_matches_curated_items_and_has_photos_on_disk():
    from pathlib import Path

    from app.mcp_tools.guides_rich import CITY_CENTERS, RICH, VENUES

    photos = Path(__file__).resolve().parents[2] / "frontend" / "public" / "photos"
    for code, rich in RICH.items():
        names = {i["name"] for i in GUIDES[code]["places"] + GUIDES[code]["adventures"]}
        assert set(rich["items"]) == names, code
        assert code in CITY_CENTERS and code in VENUES
        if photos.exists():
            assert (photos / f"{rich['hero']}.jpg").exists(), rich["hero"]
            for name, extra in rich["items"].items():
                assert (photos / f"{extra['photo']}.jpg").exists(), (code, name)


def test_nearby_venues_are_sorted_by_real_distance_and_deals_are_deterministic():
    guide = build_guide("LIS", "2026-10-01", "2026-10-08")
    for item in guide["places"] + guide["adventures"]:
        distances = [v["distance_m"] for v in item["nearby"]]
        assert distances == sorted(distances)
    again = build_guide("LIS", "2026-10-01", "2026-10-08")
    assert [v["deal"] for v in guide["venues"]] == [v["deal"] for v in again["venues"]]
    for v in guide["venues"]:
        if v["deal"]:
            assert v["deal"]["typical_price"] > v["price"]
