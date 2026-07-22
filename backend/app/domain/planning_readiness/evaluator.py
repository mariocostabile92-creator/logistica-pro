from app.domain.planning_readiness.diagnostics import (
    build_readiness_diagnostics,
)
from app.domain.planning_readiness.models import (
    PlanningReadinessEvaluationReport,
    PlanningReadinessResult,
    PlanningReadinessStatus,
)
from app.domain.planning_readiness.rules import (
    evaluate_planning_readiness_rules,
)
from app.domain.planning_readiness.scoring import (
    calculate_planning_readiness_score,
)


_RUNTIME_STATUS_MAP = {
    "stale": PlanningReadinessStatus.STALE,
    "partial": PlanningReadinessStatus.PARTIAL,
    "invalid": PlanningReadinessStatus.INVALID,
    "incompatible": PlanningReadinessStatus.INCOMPATIBLE,
    "legacy": PlanningReadinessStatus.LEGACY,
}


def _status(report, blockers, warnings):
    runtime_status = report.runtime_status.casefold()
    if runtime_status == "legacy":
        return PlanningReadinessStatus.LEGACY
    if report.workforce is None or report.fleet is None:
        return PlanningReadinessStatus.BLOCKED
    mapped = _RUNTIME_STATUS_MAP.get(runtime_status)
    if mapped is not None:
        return mapped
    if runtime_status == "missing":
        availability_blockers = {
            "WORKFORCE_AVAILABLE",
            "FLEET_AVAILABLE",
            "DEPENDENCIES_AVAILABLE",
        }
        if any(item.code in availability_blockers for item in blockers):
            return PlanningReadinessStatus.BLOCKED
        return PlanningReadinessStatus.MISSING
    if blockers:
        return PlanningReadinessStatus.BLOCKED
    if warnings:
        return PlanningReadinessStatus.WARNING
    return PlanningReadinessStatus.READY


def _rationale(status, blockers, warnings):
    if status is PlanningReadinessStatus.READY:
        return "Il piano puo essere preparato: gli input sono completi, coerenti e aggiornati."
    if status is PlanningReadinessStatus.WARNING:
        return f"Il piano e pronto con {len(warnings)} avvisi non bloccanti."
    if status is PlanningReadinessStatus.STALE:
        return "Il piano non e pronto: uno o piu snapshot non sono aggiornati."
    if status is PlanningReadinessStatus.PARTIAL:
        return "Il piano non e pronto: gli input disponibili sono parziali."
    if status is PlanningReadinessStatus.MISSING:
        return "Il piano non e pronto: mancano input necessari alla valutazione."
    if status is PlanningReadinessStatus.INVALID:
        return "Il piano non e pronto: uno o piu input non sono validi."
    if status is PlanningReadinessStatus.INCOMPATIBLE:
        return "Il piano non e pronto: gli input non descrivono lo stesso contesto operativo."
    if status is PlanningReadinessStatus.LEGACY:
        return "Il flusso Planning legacy resta attivo."
    if blockers:
        return f"Il piano non e pronto: {blockers[0].message}"
    return "Il piano non e pronto: la readiness non e determinabile."


class PlanningReadinessEvaluator:
    def evaluate(
        self,
        report: PlanningReadinessEvaluationReport,
    ) -> PlanningReadinessResult:
        rule_results = evaluate_planning_readiness_rules(report)
        score = calculate_planning_readiness_score(rule_results)
        blockers, warnings, missing_inputs, diagnostics = (
            build_readiness_diagnostics(report, rule_results)
        )
        status = _status(report, blockers, warnings)
        is_ready = status in {
            PlanningReadinessStatus.READY,
            PlanningReadinessStatus.WARNING,
        }
        envelope = report.envelope
        return PlanningReadinessResult(
            status=status,
            score=score,
            is_ready=is_ready,
            blockers=blockers,
            warnings=warnings,
            missing_inputs=missing_inputs,
            diagnostics=diagnostics,
            evaluated_at=report.evaluated_at,
            operational_unit=(
                envelope.operational_unit
                if envelope is not None
                else report.expected_operational_unit
            ),
            planning_date=(
                envelope.planning_date
                if envelope is not None
                else report.expected_planning_date
            ),
            envelope_version=(
                envelope.version.value if envelope is not None else None
            ),
            envelope_fingerprint=(
                envelope.fingerprint if envelope is not None else None
            ),
            rule_results=rule_results,
            rationale=_rationale(status, blockers, warnings),
            legacy_flow_active=report.legacy_flow_active,
        )
