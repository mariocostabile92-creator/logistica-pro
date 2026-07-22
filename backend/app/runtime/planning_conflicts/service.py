from datetime import date, datetime

from app.domain.core_language import OperationalUnit
from app.domain.planning_conflicts import (
    PlanningConflictEngine,
    PlanningConflictResult,
)
from app.runtime.planning_conflicts.contracts import (
    PlanningReadinessContextProvider,
)


class PlanningConflictService:
    def __init__(
        self,
        *,
        readiness_provider: PlanningReadinessContextProvider,
        engine: PlanningConflictEngine,
    ) -> None:
        self._readiness_provider = readiness_provider
        self._engine = engine

    def review(
        self,
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        operation_date: date,
        evaluated_at: datetime,
    ) -> PlanningConflictResult:
        context = self._readiness_provider.evaluate_with_context(
            organization_id=organization_id,
            operational_unit=operational_unit,
            operation_date=operation_date,
            evaluated_at=evaluated_at,
        )
        return self._engine.review(
            readiness=context.result,
            envelope=context.envelope,
        )
