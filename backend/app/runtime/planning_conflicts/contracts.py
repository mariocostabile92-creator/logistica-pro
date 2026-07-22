from datetime import date, datetime
from typing import Protocol

from app.domain.core_language import OperationalUnit
from app.runtime.planning_readiness import PlanningReadinessEvaluationContext


class PlanningReadinessContextProvider(Protocol):
    def evaluate_with_context(
        self,
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        operation_date: date,
        evaluated_at: datetime,
    ) -> PlanningReadinessEvaluationContext: ...
