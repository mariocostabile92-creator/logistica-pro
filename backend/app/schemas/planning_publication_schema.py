from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class PlanningPublicationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    organization_id: str = Field(default="default", min_length=1, max_length=120)
    operational_unit_id: str = Field(default="default", min_length=1, max_length=120)
    operational_unit_name: str | None = Field(default=None, max_length=120)
    planning_date: date
    confirmation_id: str = Field(min_length=1, max_length=120)
    confirmation_version: int = Field(ge=1)
    confirmation_fingerprint: str = Field(min_length=64, max_length=64)
