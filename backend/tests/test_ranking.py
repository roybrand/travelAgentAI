from app.ranking.combine import rank_and_combine
from app.ranking.score import score_flights, score_hotels

CHEAP_FAST_FLIGHT = {
    "id": "F1", "airline": "BlueSky Air", "price_per_traveler": 100, "total_price": 100,
    "duration_minutes": 120, "stops": 0,
}
PRICY_SLOW_FLIGHT = {
    "id": "F2", "airline": "Meridian Airlines", "price_per_traveler": 400, "total_price": 400,
    "duration_minutes": 600, "stops": 2,
}

BUDGET_HOTEL_NO_MATCH = {
    "id": "H1", "name": "Budget Inn", "price_per_night": 50, "rating": 3.0, "tags": ["quiet"],
}
PREMIUM_HOTEL_MATCH = {
    "id": "H2", "name": "Grand Marina", "price_per_night": 300, "rating": 4.9,
    "tags": ["beachfront", "nightlife"],
}


def test_score_flights_ranks_cheaper_faster_flight_first():
    scored = score_flights([PRICY_SLOW_FLIGHT, CHEAP_FAST_FLIGHT])
    assert scored[0]["flight"]["id"] == "F1"
    assert scored[1]["flight"]["id"] == "F2"
    assert scored[0]["score"] > scored[1]["score"]


def test_score_hotels_rewards_interest_tag_matches():
    scored = score_hotels([BUDGET_HOTEL_NO_MATCH, PREMIUM_HOTEL_MATCH], ["beachfront", "nightlife"])
    assert scored[0]["hotel"]["id"] == "H2"


def test_score_hotels_no_interests_is_neutral_match():
    scored = score_hotels([BUDGET_HOTEL_NO_MATCH], [])
    assert scored[0]["interest_match"] == 0.5


def test_rank_and_combine_picks_premium_combo_when_budget_allows():
    result = rank_and_combine(
        flights=[CHEAP_FAST_FLIGHT, PRICY_SLOW_FLIGHT],
        hotels=[BUDGET_HOTEL_NO_MATCH, PREMIUM_HOTEL_MATCH],
        nights=5,
        budget=5000,
        interests=["beachfront", "nightlife"],
    )
    assert result["chosen"]["flight"]["id"] == "F1"
    assert result["chosen"]["hotel"]["id"] == "H2"
    assert len(result["rationale"]) >= 1


def test_rank_and_combine_favors_cheaper_combo_when_budget_is_tight():
    result = rank_and_combine(
        flights=[CHEAP_FAST_FLIGHT, PRICY_SLOW_FLIGHT],
        hotels=[BUDGET_HOTEL_NO_MATCH, PREMIUM_HOTEL_MATCH],
        nights=5,
        budget=400,  # premium hotel alone (300 * 5 nights) blows this budget
        interests=[],
    )
    assert result["chosen"]["hotel"]["id"] == "H1"


def test_rank_and_combine_with_no_budget_is_neutral_budget_fit():
    result = rank_and_combine(
        flights=[CHEAP_FAST_FLIGHT],
        hotels=[PREMIUM_HOTEL_MATCH],
        nights=3,
        budget=None,
        interests=[],
    )
    assert result["chosen"]["budget_fit"] == 1
    assert result["chosen"]["total_cost"] == CHEAP_FAST_FLIGHT["total_price"] + PREMIUM_HOTEL_MATCH["price_per_night"] * 3
