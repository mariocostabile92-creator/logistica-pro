from datetime import date, datetime
from typing import Protocol

from app.domain.core_language import OperationalUnit
from app.runtime.planning_conflicts import PlanningConflictReviewContext


class PlanningConflictReviewProvider(Protocol):
    def review_with_context(
        self,
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        operation_date: date,
        evaluated_at: datetime,
    ) -> PlanningConflictReviewContext: ...
