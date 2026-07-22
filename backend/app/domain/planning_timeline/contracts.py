from datetime import datetime
from typing import Protocol

from app.domain.planning_inputs import PlanningInputSnapshot


class PlanningTimelineRuntimeStatus(Protocol):
    value: str


class PlanningTimelineCompatibility(Protocol):
    compatible: bool


class PlanningTimelineCompositionReport(Protocol):
    workforce: PlanningInputSnapshot | None
    fleet: PlanningInputSnapshot | None
    status: PlanningTimelineRuntimeStatus
    compatibility: PlanningTimelineCompatibility
    timestamp: datetime
    legacy_flow_active: bool
