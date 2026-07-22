from datetime import date, datetime

from app.domain.core_language import OperationalUnit
from app.domain.planning_inputs import PlanningInputEnvelope, PlanningInputSnapshot
from app.domain.planning_readiness.models import (
    PlanningReadinessCompatibilityCheck,
    PlanningReadinessEvaluationReport,
)


def build_planning_readiness_evaluation_report(
    *,
    runtime_status: str,
    envelope: PlanningInputEnvelope | None,
    workforce: PlanningInputSnapshot | None,
    fleet: PlanningInputSnapshot | None,
    expected_operational_unit: OperationalUnit,
    expected_planning_date: date,
    compatibility_checks: tuple[
        PlanningReadinessCompatibilityCheck, ...
    ] = (),
    runtime_warnings: tuple[str, ...] = (),
    runtime_errors: tuple[str, ...] = (),
    runtime_reasons: tuple[str, ...] = (),
    evaluated_at: datetime,
    legacy_flow_active: bool = True,
) -> PlanningReadinessEvaluationReport:
    return PlanningReadinessEvaluationReport(
        runtime_status=runtime_status,
        envelope=envelope,
        workforce=workforce,
        fleet=fleet,
        expected_operational_unit=expected_operational_unit,
        expected_planning_date=expected_planning_date,
        compatibility_checks=compatibility_checks,
        runtime_warnings=runtime_warnings,
        runtime_errors=runtime_errors,
        runtime_reasons=runtime_reasons,
        evaluated_at=evaluated_at,
        legacy_flow_active=legacy_flow_active,
    )
