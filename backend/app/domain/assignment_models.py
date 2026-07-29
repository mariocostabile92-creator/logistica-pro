from enum import Enum

from pydantic import BaseModel, Field


class AssignmentStatus(str, Enum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    WARNING = "warning"
    BLOCKED = "blocked"
    UNASSIGNED = "unassigned"
    MANUALLY_CHANGED = "manually_changed"
    INVALIDATED = "invalidated"


class AssignmentSource(str, Enum):
    HABITUAL_VEHICLE = "habitual_vehicle"
    IMPORTED_ASSIGNMENT = "imported_assignment"
    AVAILABLE_VEHICLE = "available_vehicle"
    RESERVE_VEHICLE = "reserve_vehicle"
    MANUAL = "manual"
    FALLBACK = "fallback"
    RECALCULATED = "recalculated"


class AssignmentAlternative(BaseModel):
    driver_id: str | None = None
    driver_name: str | None = None
    vehicle_id: str | None = None
    plate: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str
    not_selected_reason: str | None = None


class Assignment(BaseModel):
    id: int | None = None
    planning_id: int | None = None
    operation_date: str
    station: str
    route_id: str
    cycle_or_wave: str | None = None
    driver_id: str | None = None
    driver_name: str | None = None
    vehicle_id: str | None = None
    plate: str | None = None
    assignment_status: AssignmentStatus = AssignmentStatus.PROPOSED
    assignment_source: AssignmentSource = AssignmentSource.FALLBACK
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    data_used: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    alternatives: list[AssignmentAlternative] = Field(default_factory=list)
    manual_override: bool = False
    confirmed: bool = False
    notes: str | None = None
    created_at: str
    updated_at: str
