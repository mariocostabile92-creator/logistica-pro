from datetime import date as CalendarDate
from typing import Protocol, runtime_checkable

from app.domain.core_language import OperationalUnit
from app.domain.workforce_auto_planning.operational_demand import (
    OperationalDemand,
)
from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    WorkforceCandidateSnapshot,
)


@runtime_checkable
class OperationalDemandProvider(Protocol):
    def get_demands(
        self,
        *,
        organization_id: str,
        period_start: CalendarDate,
        period_end: CalendarDate,
        operational_unit: OperationalUnit,
    ) -> tuple[OperationalDemand, ...]: ...


@runtime_checkable
class WorkforceCandidateSnapshotProvider(Protocol):
    def get_candidates(
        self,
        *,
        organization_id: str,
        period_start: CalendarDate,
        period_end: CalendarDate,
        operational_unit: OperationalUnit,
    ) -> tuple[WorkforceCandidateSnapshot, ...]: ...
