from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, Field


class CoverageStatus(str, Enum):
    NO_FORECAST = "NO_FORECAST"
    UNDER_FORECAST = "UNDER_FORECAST"
    FORECAST_COVERED = "FORECAST_COVERED"
    REQUIREMENT_COVERED = "REQUIREMENT_COVERED"


class CoverageSource(str, Enum):
    IMPORT = "IMPORT"
    MANUAL = "MANUAL"


@dataclass(frozen=True)
class ImportedDailyCoverageRequirement:
    operational_date: str
    station: str | None
    operational_cycle: str
    coverage_segment: str | None
    forecast_routes: int
    reserve_percentage: int
    required_capacity: int
    source: str
    source_reference: str | None
    source_identity: str


class DailyCoverageRequirement(BaseModel):
    coverage_requirement_id: int
    organization_id: str
    operational_date: str
    station: str | None = None
    operational_cycle: str
    coverage_segment: str | None = None
    forecast_routes: int = Field(ge=0)
    reserve_percentage: int = Field(ge=0, le=100)
    required_capacity: int = Field(ge=0)
    source: str
    source_reference: str | None = None
    source_identity: str
    created_at: str
    updated_at: str


class DailyCoverageReadModel(BaseModel):
    operational_date: str
    cycle: str
    segment: str | None = None
    station: str | None = None
    forecast_routes: int | None = Field(default=None, ge=0)
    reserve_percentage: int | None = Field(default=None, ge=0, le=100)
    required_capacity: int | None = Field(default=None, ge=0)
    assigned_drivers: int = Field(ge=0)
    forecast_gap: int | None = Field(default=None, ge=0)
    requirement_gap: int | None = Field(default=None, ge=0)
    reserve_drivers: int | None = Field(default=None, ge=0)
    coverage_status: CoverageStatus
    source: str | None = None
    source_reference: str | None = None


class DailyCoverageSummary(BaseModel):
    forecast_total: int = Field(ge=0)
    requirement_total: int = Field(ge=0)
    assigned_total: int = Field(ge=0)
    forecast_gap_total: int = Field(ge=0)
    requirement_gap_total: int = Field(ge=0)
    reserve_total: int = Field(ge=0)
    forecast_available_buckets: int = Field(ge=0)
    no_forecast_buckets: int = Field(ge=0)


class DailyCoverageResponse(BaseModel):
    date_from: str
    date_to: str
    cycle: str | None = None
    items: list[DailyCoverageReadModel] = Field(default_factory=list)
    summary: DailyCoverageSummary
