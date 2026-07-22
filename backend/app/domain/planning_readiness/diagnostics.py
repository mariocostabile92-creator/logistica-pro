from datetime import timedelta

from app.domain.planning_inputs import PlanningInputStatus, WorkforcePlanningInput

from app.domain.planning_readiness.models import (
    PlanningReadinessBlocker,
    PlanningReadinessDiagnostic,
    PlanningReadinessEvaluationReport,
    PlanningReadinessMissingInput,
    PlanningReadinessRuleResult,
    PlanningReadinessSeverity,
    PlanningReadinessWarning,
)
from app.domain.planning_readiness.rules import readiness_rule


FRESHNESS_WARNING_WINDOW = timedelta(minutes=15)


def _unique(items):
    values = {}
    for item in items:
        values[(item.code, item.source)] = item
    return tuple(values.values())


def _rule_issues(rule_results):
    blockers = []
    warnings = []
    for result in rule_results:
        if result.passed is not False:
            continue
        rule = readiness_rule(result.code)
        values = {
            "code": rule.code,
            "category": rule.category,
            "message": rule.failure_message,
            "rationale": rule.rationale,
            "source": rule.source,
            "remediation_hint": rule.remediation_hint,
        }
        if rule.blocking:
            blockers.append(PlanningReadinessBlocker(**values))
        else:
            warnings.append(PlanningReadinessWarning(**values))
    return blockers, warnings


def _validation_issues(report):
    blockers = []
    warnings = []
    for label, snapshot in (
        ("workforce", report.workforce),
        ("fleet", report.fleet),
    ):
        if snapshot is None:
            continue
        for issue in snapshot.validation.issues:
            values = {
                "code": issue.code,
                "category": "validation",
                "message": issue.message,
                "rationale": (
                    f"Validazione {label}"
                    + (f" sul campo {issue.field}." if issue.field else ".")
                ),
                "source": label,
                "remediation_hint": (
                    f"Correggi il dato {label} indicato e aggiorna lo snapshot."
                ),
            }
            target = blockers if issue.blocking else warnings
            model = PlanningReadinessBlocker if issue.blocking else PlanningReadinessWarning
            target.append(model(**values))
    return blockers, warnings


def _freshness_warnings(report):
    warnings = []
    for label, snapshot in (
        ("workforce", report.workforce),
        ("fleet", report.fleet),
    ):
        if snapshot is None or snapshot.validation.status is PlanningInputStatus.STALE:
            continue
        expires_at = snapshot.contract.metadata.freshness.expires_at
        remaining = expires_at - report.evaluated_at
        if timedelta(0) <= remaining <= FRESHNESS_WARNING_WINDOW:
            warnings.append(
                PlanningReadinessWarning(
                    code="SNAPSHOT_EXPIRING_SOON",
                    category="freshness",
                    message=f"Lo snapshot {label.title()} e vicino alla scadenza.",
                    rationale="La finestra di freshness residua e inferiore a 15 minuti.",
                    source=label,
                    remediation_hint=f"Aggiorna {label.title()} prima della conferma.",
                )
            )
    return warnings


def _coverage_warnings(report):
    if report.workforce is None:
        return []
    payload = report.workforce.contract.payload
    if not isinstance(payload, WorkforcePlanningInput):
        return []
    coverage = payload.coverage
    if coverage is None or coverage.margin is None or coverage.margin >= 0:
        return []
    return [
        PlanningReadinessWarning(
            code="REDUCED_WORKFORCE_COVERAGE",
            category="availability",
            message=f"Copertura Workforce ridotta di {abs(coverage.margin)} risorse.",
            rationale="La disponibilita e inferiore al fabbisogno osservato.",
            source="workforce",
            remediation_hint="Verifica assenze e copertura nel Workspace Workforce.",
        )
    ]


def _optional_dependency_warnings(report):
    warnings = []
    for label, snapshot in (
        ("workforce", report.workforce),
        ("fleet", report.fleet),
    ):
        if snapshot is None:
            continue
        for dependency in snapshot.contract.dependencies:
            if dependency.required or dependency.satisfied:
                continue
            warnings.append(
                PlanningReadinessWarning(
                    code="OPTIONAL_DEPENDENCY_MISSING",
                    category="dependency",
                    message=f"Dipendenza opzionale {dependency.dependency_id} non disponibile.",
                    rationale="La dipendenza e dichiarata ma non e bloccante.",
                    source=label,
                    remediation_hint="Verifica la dipendenza prima della conferma, se necessaria.",
                )
            )
    return warnings


def build_missing_inputs(report):
    missing = []
    for label, snapshot in (
        ("Workforce", report.workforce),
        ("Fleet", report.fleet),
    ):
        if snapshot is not None and snapshot.validation.status is not PlanningInputStatus.MISSING:
            continue
        missing.append(
            PlanningReadinessMissingInput(
                code=f"{label.upper()}_INPUT_MISSING",
                category="input",
                message=f"Input {label} non disponibile.",
                rationale=f"Lo snapshot {label} e assente o privo dei dati minimi.",
                source=label.casefold(),
                severity=PlanningReadinessSeverity.CRITICAL,
                remediation_hint=f"Apri {label} e aggiorna i dati operativi.",
                input_name=label.casefold(),
            )
        )
    return _unique(missing)


def build_readiness_diagnostics(
    report: PlanningReadinessEvaluationReport,
    rule_results: tuple[PlanningReadinessRuleResult, ...],
) -> tuple[
    tuple[PlanningReadinessBlocker, ...],
    tuple[PlanningReadinessWarning, ...],
    tuple[PlanningReadinessMissingInput, ...],
    tuple[PlanningReadinessDiagnostic, ...],
]:
    blockers, warnings = _rule_issues(rule_results)
    validation_blockers, validation_warnings = _validation_issues(report)
    blockers.extend(validation_blockers)
    warnings.extend(validation_warnings)
    warnings.extend(_freshness_warnings(report))
    warnings.extend(_coverage_warnings(report))
    warnings.extend(_optional_dependency_warnings(report))
    blockers = list(_unique(blockers))
    warnings = list(_unique(warnings))
    missing_inputs = build_missing_inputs(report)

    diagnostics = [
        PlanningReadinessDiagnostic.model_validate(item.model_dump())
        for item in (*blockers, *warnings)
    ]
    for check in report.compatibility_checks:
        if check.compatible is not False:
            continue
        diagnostics.append(
            PlanningReadinessDiagnostic(
                code=check.code,
                category="compatibility",
                message=check.message,
                rationale="Controllo esplicito del Runtime Composition.",
                source="runtime-composition",
                severity=PlanningReadinessSeverity.CRITICAL,
                remediation_hint="Allinea gli input e rigenera la composizione.",
            )
        )
    for index, message in enumerate(report.runtime_errors, start=1):
        diagnostics.append(
            PlanningReadinessDiagnostic(
                code=f"RUNTIME_ERROR_{index}",
                category="runtime",
                message=message,
                rationale="Il Runtime Composition ha segnalato un errore controllato.",
                source="runtime-composition",
                severity=PlanningReadinessSeverity.CRITICAL,
                remediation_hint="Aggiorna le sorgenti e riprova.",
            )
        )
    return (
        tuple(blockers),
        tuple(warnings),
        missing_inputs,
        _unique(diagnostics),
    )
