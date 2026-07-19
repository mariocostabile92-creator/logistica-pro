from enum import Enum

from pydantic import BaseModel, Field

from app.domain.assignment_models import Assignment
from app.domain.planning_diff import PlanningDiff


class OperationEventType(str, Enum):
    DRIVER_ABSENT = "driver_absent"
    DRIVER_RESTORED = "driver_restored"
    VEHICLE_UNAVAILABLE = "vehicle_unavailable"
    VEHICLE_RESTORED = "vehicle_restored"
    ROUTE_ABORTED = "route_aborted"
    ROUTE_ADDED = "route_added"
    VEHICLE_CHANGED = "vehicle_changed"
    DRIVER_CHANGED = "driver_changed"


class OperationEntityType(str, Enum):
    DRIVER = "driver"
    VEHICLE = "vehicle"
    ROUTE = "route"
    ASSIGNMENT = "assignment"


class OperationEvent(BaseModel):
    event_id: int | None = None
    planning_id: int
    event_type: OperationEventType
    entity_type: OperationEntityType
    entity_id: str
    reason: str
    simulated: bool = True
    applied: bool = False
    impact_summary: str
    payload: dict[str, object] = Field(default_factory=dict)
    actor: str = "local_operator"
    created_at: str
    applied_at: str | None = None


class EventSimulation(BaseModel):
    event: OperationEvent
    diff: PlanningDiff
    proposed_assignments: list[Assignment] = Field(default_factory=list)
