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
