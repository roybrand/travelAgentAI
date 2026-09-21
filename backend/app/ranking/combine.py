from .score import score_combo, score_flights, score_hotels

TOP_N_PER_CATEGORY = 3


def rank_and_combine(
    flights: list[dict],
    hotels: list[dict],
    nights: int,
    budget: float | None,
    interests: list[str],
) -> dict:
    """The "optimize combinations / rank" step from the requirements: take the best
    few flights and best few hotels independently, score every pairing together
    against the trip budget, and return the winner plus alternatives.
    """
    top_flights = score_flights(flights)[:TOP_N_PER_CATEGORY]
    top_hotels = score_hotels(hotels, interests)[:TOP_N_PER_CATEGORY]

    combos = [
        score_combo(flight_scored, hotel_scored, nights, budget)
        for flight_scored in top_flights
        for hotel_scored in top_hotels
    ]
    combos.sort(key=lambda c: c["final_score"], reverse=True)

    chosen = combos[0]
    alternatives = combos[1:4]
    runner_up = next((c for c in combos if c["hotel"]["id"] != chosen["hotel"]["id"]), None)

    chosen["pros"], chosen["cons"] = _pros_cons_for_chosen(chosen, combos, flights, hotels, interests, budget)
    for alt in alternatives:
        alt["pros"], alt["cons"] = _compare_to_chosen(alt, chosen, interests)

    return {
        "chosen": chosen,
        "alternatives": alternatives,
        "rationale": _build_rationale(chosen, runner_up, interests),
    }


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _hm(minutes: float) -> str:
    minutes = round(minutes)
    return f"{minutes // 60}h {minutes % 60:02d}m"


def _stops_text(stops: int) -> str:
    return "a direct flight" if stops == 0 else f"{stops} stop{'s' if stops > 1 else ''}"


def _matched(hotel: dict, interests: list[str]) -> list[str]:
    return [tag for tag in interests if tag in hotel["tags"]]


def _pros_cons_for_chosen(
    chosen: dict,
    combos: list[dict],
    flights: list[dict],
    hotels: list[dict],
    interests: list[str],
    budget: float | None,
) -> tuple[list[str], list[str]]:
    """Plain-language strengths and drawbacks of the chosen pick, each derived from a
    concrete number in the search results (no generic filler)."""
    flight, hotel = chosen["flight"], chosen["hotel"]
    avg_price = _mean([f["price_per_traveler"] for f in flights])
    avg_duration = _mean([f["duration_minutes"] for f in flights])
    avg_hotel_price = _mean([h["price_per_night"] for h in hotels])
    cheapest = min(c["total_cost"] for c in combos)
    distance = hotel.get("distance_to_center_km")
    matched = _matched(hotel, interests)
    pros, cons = [], []

    if flight["stops"] == 0:
        pros.append("Direct flight, no connections")
    elif flight["stops"] == 1:
        pros.append("Only one connection")
    else:
        cons.append(f"{flight['stops']} stops make for a long journey")

    if flight["price_per_traveler"] < avg_price:
        pros.append(f"Flight is £{avg_price - flight['price_per_traveler']:.0f} per traveler below the average of options found")
    elif flight["price_per_traveler"] > avg_price:
        cons.append(f"Flight is £{flight['price_per_traveler'] - avg_price:.0f} per traveler above the average of options found")

    if flight["duration_minutes"] <= avg_duration - 15:
        pros.append(f"Faster than average journey ({_hm(flight['duration_minutes'])})")
    elif flight["duration_minutes"] >= avg_duration + 15:
        cons.append(f"Longer than average journey ({_hm(flight['duration_minutes'])})")

    if hotel["rating"] >= 4.5:
        pros.append(f"Top-rated hotel ({hotel['rating']} out of 5)")
    elif hotel["rating"] < 4.0:
        cons.append(f"Below-average hotel rating ({hotel['rating']} out of 5)")

    if interests:
        missing = [tag for tag in interests if tag not in matched]
        if matched:
            pros.append(f"Matches {len(matched)} of {len(interests)} interests: {', '.join(matched)}")
        if missing:
            cons.append(f"Does not cover: {', '.join(missing)}")

    if distance is not None:
        if distance <= 2:
            pros.append(f"Central location, {distance} km from the centre")
        elif distance > 5:
            cons.append(f"Far from the centre ({distance} km)")

    if hotel["price_per_night"] > avg_hotel_price * 1.15:
        cons.append(f"Hotel rate is above average (£{hotel['price_per_night']:.0f} vs £{avg_hotel_price:.0f} per night)")

    if budget:
        gap = budget - chosen["total_cost"]
        if gap > 0:
            pros.append(f"£{gap:.0f} under your budget")
        elif gap < 0:
            cons.append(f"£{-gap:.0f} over your budget")

    extra = chosen["total_cost"] - cheapest
    if extra > 0:
        cons.append(f"£{extra:.0f} more than the cheapest combination scored")
    else:
        pros.append("Cheapest combination among the shortlisted options")

    return (
        pros or ["Solid all-round balance of price, rating and interests"],
        cons or ["No significant drawbacks against your criteria"],
    )


def _compare_to_chosen(alt: dict, chosen: dict, interests: list[str]) -> tuple[list[str], list[str]]:
    """How an alternative differs from the best match, one line per real difference."""
    pros, cons = [], []

    diff = alt["total_cost"] - chosen["total_cost"]
    if diff < 0:
        pros.append(f"£{-diff:.0f} cheaper overall")
    elif diff > 0:
        cons.append(f"£{diff:.0f} more expensive overall")

    a_flight, c_flight = alt["flight"], chosen["flight"]
    if a_flight["stops"] < c_flight["stops"]:
        pros.append(f"Fewer stops ({_stops_text(a_flight['stops'])} vs {_stops_text(c_flight['stops'])})")
    elif a_flight["stops"] > c_flight["stops"]:
        cons.append(f"More stops ({_stops_text(a_flight['stops'])} vs {_stops_text(c_flight['stops'])})")

    time_gap = a_flight["duration_minutes"] - c_flight["duration_minutes"]
    if time_gap <= -30:
        pros.append(f"{_hm(-time_gap)} faster journey")
    elif time_gap >= 30:
        cons.append(f"{_hm(time_gap)} slower journey")

    a_hotel, c_hotel = alt["hotel"], chosen["hotel"]
    rating_gap = a_hotel["rating"] - c_hotel["rating"]
    if rating_gap >= 0.2:
        pros.append(f"Higher-rated hotel ({a_hotel['rating']} vs {c_hotel['rating']})")
    elif rating_gap <= -0.2:
        cons.append(f"Lower-rated hotel ({a_hotel['rating']} vs {c_hotel['rating']})")

    interest_gap = len(_matched(a_hotel, interests)) - len(_matched(c_hotel, interests))
    if interest_gap > 0:
        pros.append("Matches more of your interests")
    elif interest_gap < 0:
        cons.append("Matches fewer of your interests")

    a_dist, c_dist = a_hotel.get("distance_to_center_km"), c_hotel.get("distance_to_center_km")
    if a_dist is not None and c_dist is not None:
        if a_dist <= c_dist - 1:
            pros.append(f"Closer to the centre ({a_dist} km vs {c_dist} km)")
        elif a_dist >= c_dist + 1:
            cons.append(f"Farther from the centre ({a_dist} km vs {c_dist} km)")

    return (
        pros or ["Comparable to the best match on price, journey and hotel"],
        cons or ["Scores slightly lower overall than the best match"],
    )


def _build_rationale(chosen: dict, runner_up: dict | None, interests: list[str]) -> list[str]:
    notes = []
    stops = chosen["flight"]["stops"]
    stops_text = "direct" if stops == 0 else f"{stops} stop(s)"
    notes.append(
        f"Total estimated cost £{chosen['total_cost']:.0f} via {chosen['flight']['airline']} "
        f"({stops_text}) + {chosen['hotel']['name']}."
    )

    if runner_up:
        price_diff = chosen["hotel"]["price_per_night"] - runner_up["hotel"]["price_per_night"]
        rating_diff = chosen["hotel"]["rating"] - runner_up["hotel"]["rating"]
        matched_tags = [tag for tag in interests if tag in chosen["hotel"]["tags"]]

        if price_diff == 0:
            price_clause = "costs the same per night as"
        else:
            price_clause = f"is £{abs(price_diff):.0f} {'more' if price_diff > 0 else 'less'} per night than"

        if rating_diff == 0:
            rating_clause = "the same rating as"
        else:
            rating_clause = (
                f"a {'higher' if rating_diff > 0 else 'lower'} rating "
                f"({chosen['hotel']['rating']} vs {runner_up['hotel']['rating']}) than"
            )

        sentence = f"{chosen['hotel']['name']} {price_clause} {runner_up['hotel']['name']}, with {rating_clause} it."
        if matched_tags:
            sentence += f" It also matches your interests: {', '.join(matched_tags)}."
        notes.append(sentence)

    return notes
