from typing import Any, TypedDict


class TripState(TypedDict, total=False):
    request: dict[str, Any]
    nights: int
    flights: list[dict]
    hotels: list[dict]
    guide: dict | None
    ranking: dict
    itinerary: dict
