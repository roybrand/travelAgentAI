# Scoring model implementing the "AI ranking" idea from the requirements: instead of
# just picking the cheapest option, score price + quality + interest-match + overall
# budget fit, so a combo that costs a bit more but fits the traveler better can
# outrank the cheapest one.


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _range(values: list[float]) -> tuple[float, float]:
    return min(values), max(values)


def _inverse_normalize(value: float, lo: float, hi: float) -> float:
    """Higher raw value -> lower score (cheaper/faster wins). Flat range -> neutral 1."""
    if hi == lo:
        return 1.0
    return clamp((hi - value) / (hi - lo), 0.0, 1.0)


def score_flights(flights: list[dict]) -> list[dict]:
    lo_price, hi_price = _range([f["price_per_traveler"] for f in flights])
    lo_dur, hi_dur = _range([f["duration_minutes"] for f in flights])

    scored = []
    for flight in flights:
        price_score = _inverse_normalize(flight["price_per_traveler"], lo_price, hi_price)
        duration_score = _inverse_normalize(flight["duration_minutes"], lo_dur, hi_dur)
        score = price_score * 0.6 + duration_score * 0.4
        scored.append({
            "flight": flight,
            "score": score,
            "price_score": price_score,
            "duration_score": duration_score,
        })

    return sorted(scored, key=lambda s: s["score"], reverse=True)


def score_hotels(hotels: list[dict], interests: list[str] | None = None) -> list[dict]:
    interests = interests or []
    lo_price, hi_price = _range([h["price_per_night"] for h in hotels])

    scored = []
    for hotel in hotels:
        price_score = _inverse_normalize(hotel["price_per_night"], lo_price, hi_price)
        # Guest rating if a provider supplies one, else the OpenStreetMap star class, else a neutral 3.5
        quality = hotel.get("rating") if hotel.get("rating") is not None else hotel.get("stars")
        rating_score = (quality if quality is not None else 3.5) / 5
        if interests:
            interest_match = len(set(interests) & set(hotel["tags"])) / len(interests)
        else:
            interest_match = 0.5

        score = price_score * 0.35 + rating_score * 0.35 + interest_match * 0.30
        scored.append({
            "hotel": hotel,
            "score": score,
            "price_score": price_score,
            "rating_score": rating_score,
            "interest_match": interest_match,
        })

    return sorted(scored, key=lambda s: s["score"], reverse=True)


def score_combo(flight_scored: dict, hotel_scored: dict, nights: int, budget: float | None) -> dict:
    total_cost = flight_scored["flight"]["total_price"] + hotel_scored["hotel"]["price_per_night"] * nights
    budget_fit = clamp(1 - max(0.0, total_cost - budget) / budget, 0.0, 1.0) if budget else 1.0
    final_score = flight_scored["score"] * 0.3 + hotel_scored["score"] * 0.5 + budget_fit * 0.2

    return {
        "flight": flight_scored["flight"],
        "hotel": hotel_scored["hotel"],
        "total_cost": total_cost,
        "budget_fit": budget_fit,
        "final_score": final_score,
        "breakdown": {
            "flight_score": flight_scored["score"],
            "hotel_score": hotel_scored["score"],
            "budget_fit": budget_fit,
        },
    }
