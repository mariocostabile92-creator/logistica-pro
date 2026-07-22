from datetime import date, datetime

from app.domain.core_language import OperationalUnit
from app.domain.planning_readiness import (
    PlanningReadinessCompatibilityCheck,
    PlanningReadinessEvaluator,
    PlanningReadinessResult,
    build_planning_readiness_evaluation_report,
)
from app.runtime.planning_readiness.contracts import (
    PlanningInputCompositionProvider,
)
from app.runtime.planning_readiness.models import (
    PlanningReadinessEvaluationContext,
)


class PlanningReadinessService:
    def __init__(
        self,
        *,
        composition_provider: PlanningInputCompositionProvider,
        evaluator: PlanningReadinessEvaluator,
    ) -> None:
        self._composition_provider = composition_provider
        self._evaluator = evaluator

    def evaluate(
        self,
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        operation_date: date,
        evaluated_at: datetime,
    ) -> PlanningReadinessResult:
        return self.evaluate_with_context(
            organization_id=organization_id,
            operational_unit=operational_unit,
            operation_date=operation_date,
            evaluated_at=evaluated_at,
        ).result

    def evaluate_with_context(
        self,
        *,
        organization_id: str,
        operational_unit: OperationalUnit,
        operation_date: date,
        evaluated_at: datetime,
    ) -> PlanningReadinessEvaluationContext:
        composition = self._composition_provider.compose(
            organization_id=organization_id,
            operational_unit=operational_unit,
            operation_date=operation_date,
            composed_at=evaluated_at,
        )
        report = build_planning_readiness_evaluation_report(
            runtime_status=composition.status.value,
            envelope=composition.envelope,
            workforce=composition.report.workforce,
            fleet=composition.report.fleet,
            expected_operational_unit=operational_unit,
            expected_planning_date=operation_date,
            compatibility_checks=tuple(
                PlanningReadinessCompatibilityCheck(
                    code=item.code,
                    compatible=item.compatible,
                    message=item.message,
                )
                for item in composition.compatibility.checks
            ),
            runtime_warnings=composition.diagnostics.warnings,
            runtime_errors=composition.diagnostics.errors,
            runtime_reasons=composition.diagnostics.reasons,
            evaluated_at=evaluated_at,
            legacy_flow_active=composition.legacy_flow_active,
        )
        return PlanningReadinessEvaluationContext(
            result=self._evaluator.evaluate(report),
            envelope=composition.envelope,
        )
