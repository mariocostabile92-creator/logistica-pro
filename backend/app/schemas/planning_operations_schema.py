from typing import Literal

from pydantic import BaseModel, Field


class ForecastDay(BaseModel):
    operation_date: str
    routes_expected: int = Field(ge=0)


class ForecastRequest(BaseModel):
    station: str = Field(min_length=1, max_length=80)
    source_filename: str = Field(min_length=1, max_length=255)
    days: list[ForecastDay] = Field(min_length=1, max_length=90)


class ConvocationRequest(BaseModel):
    status: Literal["da_preparare", "pronta", "inviata", "confermata"]
    scheduled_time: str | None = Field(default=None, max_length=16)


class OperationalLifecycleRequest(BaseModel):
    actor: str = Field(default="local_operator", min_length=1, max_length=120)


class PlanningOperationResponse(BaseModel):
    planning: dict[str, object] | None = None
    summary: dict[str, object]
    routes: list[dict[str, object]] = Field(default_factory=list)
    conflicts: list[dict[str, object]] = Field(default_factory=list)
    convocations: list[dict[str, object]] = Field(default_factory=list)
    forecast: dict[str, object] | None = None
    workforce: dict[str, object]
    lifecycle: dict[str, object]
    audit: list[dict[str, object]] = Field(default_factory=list)
    permissions: dict[str, bool]
