from pydantic import BaseModel, Field

from app.domain.planning_models import StationCapacity


class AssignmentChange(BaseModel):
    assignment_id: int | None = None
    route_id: str
    change_type: str
    before: dict[str, object] | None = None
    after: dict[str, object] | None = None
    changed_fields: list[str] = Field(default_factory=list)


class PlanningDiff(BaseModel):
    planning_id: int
    event_type: str
    summary: str
    assignment_changes: list[AssignmentChange] = Field(default_factory=list)
    station_capacity_before: list[StationCapacity] = Field(default_factory=list)
    station_capacity_after: list[StationCapacity] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
