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

    @model_validator(mode="after")
    def check_dates(self):
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self
