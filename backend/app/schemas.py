from datetime import date

from pydantic import BaseModel, Field, model_validator


class TripRequest(BaseModel):
    origin: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    start_date: date
    end_date: date
    budget: float | None = Field(default=None, gt=0)
    travelers: int = Field(default=1, ge=1)
    interests: list[str] = Field(default_factory=list)
    place_types: list[str] = Field(default_factory=list, max_length=14)

    @model_validator(mode="after")
    def check_dates(self):
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class ParseRequest(BaseModel):
    text: str = Field(min_length=3, max_length=1200)


class PlannedItem(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class NearbyRequest(BaseModel):
    """A position and the traveler's context. Only sent after they turn 'Nearby now' on."""
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    radius_m: int = Field(default=1500, ge=200, le=5000)
    interests: list[str] = Field(default_factory=list, max_length=12)
    planned: list[PlannedItem] = Field(default_factory=list, max_length=30)


class BuildRequest(BaseModel):
    """Free text and an optional photo (a small JPEG/PNG/WebP data URL) for the trip builder."""
    text: str = Field(default="", max_length=1500)
    image: str | None = Field(default=None, max_length=2_000_000)
