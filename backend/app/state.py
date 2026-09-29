from typing import Any, TypedDict


class TripState(TypedDict, total=False):
    request: dict[str, Any]
    nights: int
    flights: list[dict]
    hotels: list[dict]
    hotel_segments: list[dict]
    guide: dict | None
    guide_segments: list[dict]
    flights_source: dict
    hotels_source: dict
    ranking: dict
    itinerary: dict
    planning_rules: dict
    route_repair_attempted: bool
    route_repair: dict
    itinerary_validation: dict


class ParseRequestState(TypedDict, total=False):
    text: str
    today: Any
    parsed: dict[str, Any]


class BuildTripState(TypedDict, total=False):
    text: str
    image: str | None
    today: Any
    built: dict[str, Any]
