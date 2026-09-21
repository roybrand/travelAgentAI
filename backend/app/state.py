from typing import Any, TypedDict


class TripState(TypedDict, total=False):
    request: dict[str, Any]
    nights: int
    flights: list[dict]
    hotels: list[dict]
    guide: dict | None
    flights_source: dict
    hotels_source: dict
    ranking: dict
    itinerary: dict
