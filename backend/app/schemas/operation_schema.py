from pydantic import BaseModel, Field

from app.domain.normalized_models import OperationConflict


class OperationSummary(BaseModel):
    routes: int = 0
    drivers: int = 0
    operational_vehicles: int = 0
    reserve_vehicles: int = 0
    critical_conflicts: int = 0
    warnings: int = 0
    unrecognized_rows: int = 0


class AnalyzeRequest(BaseModel):
    planning_rows: list[dict[str, object]] | None = None
    fleet_rows: list[dict[str, object]] | None = None
    reserve_threshold: int = Field(default=1, ge=0, le=1000)


class AnalyzeResponse(BaseModel):
    analysis_id: int | None = None
    summary: OperationSummary
    conflicts: list[OperationConflict] = Field(default_factory=list)
