from datetime import date, datetime
from typing import Protocol

from app.domain.core_language import OperationalUnit
from app.domain.planning_conflicts import PlanningConflictResult
from app.domain.planning_drafts import PlanningDraftWorkspace
from app.domain.planning_inputs import PlanningInputEnvelope
from app.domain.planning_readiness import PlanningReadinessResult
from app.runtime.planning_readiness import PlanningReadinessEvaluationContext


class PlanningDraftProvider(Protocol):
    def current(
        self,
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        planning_date: date,
    ) -> PlanningDraftWorkspace: ...


class PlanningReadinessContextProvider(Protocol):
    def evaluate_with_context(
        self,
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        operation_date: date,
        evaluated_at: datetime,
    ) -> PlanningReadinessEvaluationContext: ...


class PlanningConflictReviewer(Protocol):
    def review(
        self,
        *,
        readiness: PlanningReadinessResult,
        envelope: PlanningInputEnvelope | None,
    ) -> PlanningConflictResult: ...
