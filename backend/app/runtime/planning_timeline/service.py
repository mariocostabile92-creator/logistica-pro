from datetime import date, datetime

from app.domain.core_language import OperationalUnit
from app.domain.planning_timeline import (
    PlanningTimelineEngine,
    PlanningTimelineResult,
)
from app.runtime.planning_timeline.contracts import (
    PlanningConflictReviewProvider,
)


class PlanningTimelineRuntimeService:
    def __init__(
        self,
        *,
        review_provider: PlanningConflictReviewProvider,
        engine: PlanningTimelineEngine,
    ) -> None:
        self._review_provider = review_provider
        self._engine = engine

    def timeline(
        self,
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        operation_date: date,
        evaluated_at: datetime,
    ) -> PlanningTimelineResult:
        context = self._review_provider.review_with_context(
            organization_id=organization_id,
            operational_unit=operational_unit,
            operation_date=operation_date,
            evaluated_at=evaluated_at,
        )
        return self._engine.build(
            readiness=context.readiness,
            conflicts=context.result.report,
            composition=context.composition_report,
            evaluated_at=context.evaluated_at,
        )
