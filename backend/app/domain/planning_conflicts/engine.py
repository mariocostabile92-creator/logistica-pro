from app.domain.planning_conflicts.evaluator import PlanningConflictEvaluator
from app.domain.planning_conflicts.grouping import (
    group_planning_conflicts,
    sort_planning_conflicts,
)
from app.domain.planning_conflicts.models import (
    PlanningConflictReadiness,
    PlanningConflictReport,
    PlanningConflictResult,
)
from app.domain.planning_inputs import PlanningInputEnvelope
from app.domain.planning_readiness import PlanningReadinessResult


class PlanningConflictEngine:
    def __init__(self, evaluator: PlanningConflictEvaluator) -> None:
        self._evaluator = evaluator

    def review(
        self,
        *,
        readiness: PlanningReadinessResult,
        envelope: PlanningInputEnvelope | None,
    ) -> PlanningConflictResult:
        conflicts = sort_planning_conflicts(
            self._evaluator.evaluate(readiness, envelope)
        )
        blocking = sum(item.blocking for item in conflicts)
        report = PlanningConflictReport(
            total_conflicts=len(conflicts),
            total_blocking=blocking,
            total_warnings=len(conflicts) - blocking,
            groups=group_planning_conflicts(conflicts),
            conflicts=conflicts,
            timestamp=readiness.evaluated_at,
            planning_version=readiness.envelope_version,
            planning_date=readiness.planning_date,
            operational_unit=readiness.operational_unit,
        )
        return PlanningConflictResult(
            readiness=PlanningConflictReadiness.from_readiness(readiness),
            report=report,
        )
