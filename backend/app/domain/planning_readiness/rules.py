from collections.abc import Callable

from app.domain.planning_inputs import (
    PLANNING_INPUT_CONTRACT_VERSION,
    FleetPlanningInput,
    PlanningInputStatus,
    WorkforcePlanningInput,
    planning_input_envelope_fingerprint,
    planning_input_fingerprint,
)

from app.domain.planning_readiness.models import (
    PlanningReadinessEvaluationReport,
    PlanningReadinessRule,
    PlanningReadinessRuleResult,
    PlanningReadinessSeverity,
)


def _rule(
    code: str,
    category: str,
    description: str,
    weight: int,
    *,
    blocking: bool,
    failure_message: str,
    rationale: str,
    remediation_hint: str,
    source: str = "planning-input",
) -> PlanningReadinessRule:
    return PlanningReadinessRule(
        code=code,
        category=category,
        description=description,
        source=source,
        weight=weight,
        blocking=blocking,
        failure_message=failure_message,
        rationale=rationale,
        remediation_hint=remediation_hint,
    )


PLANNING_READINESS_RULES = (
    _rule(
        "ENVELOPE_PRESENT",
        "input",
        "Planning Input Envelope disponibile.",
        4,
        blocking=True,
        failure_message="Il Planning Input Envelope non e disponibile.",
        rationale="La readiness richiede un envelope composto dal Runtime.",
        remediation_hint="Aggiorna Workforce e Fleet, poi riprova.",
        source="runtime-composition",
    ),
    _rule(
        "ENVELOPE_VALIDATED",
        "validation",
        "Tutti gli input dell'envelope sono validati.",
        6,
        blocking=True,
        failure_message="L'envelope non contiene input completamente validati.",
        rationale="Un input non validato non puo supportare la conferma del piano.",
        remediation_hint="Risolvi gli errori di validazione indicati.",
    ),
    _rule(
        "RUNTIME_COMPATIBLE",
        "runtime",
        "Lo stato Runtime e compatibile con la valutazione.",
        10,
        blocking=True,
        failure_message="Gli input Runtime non sono compatibili.",
        rationale="Scope, contratti e sorgenti devono essere coerenti.",
        remediation_hint="Allinea Operational Unit, data, versioni e sorgenti.",
        source="runtime-composition",
    ),
    _rule(
        "WORKFORCE_PRESENT",
        "completeness",
        "Snapshot Workforce presente.",
        5,
        blocking=True,
        failure_message="Manca lo snapshot Workforce.",
        rationale="Il piano richiede risorse umane osservate.",
        remediation_hint="Apri Workforce e aggiorna i dati operativi.",
        source="workforce",
    ),
    _rule(
        "FLEET_PRESENT",
        "completeness",
        "Snapshot Fleet presente.",
        5,
        blocking=True,
        failure_message="Manca lo snapshot Fleet.",
        rationale="Il piano richiede Asset osservati.",
        remediation_hint="Apri Fleet e aggiorna il parco mezzi.",
        source="fleet",
    ),
    _rule(
        "OPERATIONAL_UNIT_MATCH",
        "scope",
        "Operational Unit coerente tra gli input.",
        5,
        blocking=True,
        failure_message="Operational Unit non coerente tra Workforce e Fleet.",
        rationale="Gli input devono descrivere lo stesso perimetro operativo.",
        remediation_hint="Seleziona e aggiorna la stessa Operational Unit.",
    ),
    _rule(
        "PLANNING_DATE_MATCH",
        "scope",
        "Data operativa coerente tra gli input.",
        5,
        blocking=True,
        failure_message="Data operativa non coerente tra Workforce e Fleet.",
        rationale="Gli input devono riferirsi alla stessa giornata.",
        remediation_hint="Aggiorna entrambi gli input per la data selezionata.",
    ),
    _rule(
        "WORKFORCE_FRESH",
        "freshness",
        "Snapshot Workforce non scaduto.",
        5,
        blocking=True,
        failure_message="Lo snapshot Workforce e scaduto.",
        rationale="Una disponibilita non aggiornata non e affidabile.",
        remediation_hint="Aggiorna Workforce.",
        source="workforce",
    ),
    _rule(
        "FLEET_FRESH",
        "freshness",
        "Snapshot Fleet non scaduto.",
        5,
        blocking=True,
        failure_message="Lo snapshot Fleet e scaduto.",
        rationale="Una disponibilita Asset non aggiornata non e affidabile.",
        remediation_hint="Aggiorna Fleet.",
        source="fleet",
    ),
    _rule(
        "WORKFORCE_COMPLETE",
        "completeness",
        "Snapshot Workforce completo.",
        4,
        blocking=False,
        failure_message="Lo snapshot Workforce e parziale.",
        rationale="Alcuni dati Workforce richiesti non sono disponibili.",
        remediation_hint="Completa copertura, disponibilita e finestre orarie.",
        source="workforce",
    ),
    _rule(
        "FLEET_COMPLETE",
        "completeness",
        "Snapshot Fleet completo.",
        4,
        blocking=False,
        failure_message="Lo snapshot Fleet e parziale.",
        rationale="Alcuni dati Fleet richiesti non sono disponibili.",
        remediation_hint="Completa Registry e disponibilita Asset.",
        source="fleet",
    ),
    _rule(
        "WORKFORCE_AVAILABLE",
        "availability",
        "Almeno una Human Resource e disponibile.",
        10,
        blocking=True,
        failure_message="Nessuna Human Resource risulta disponibile.",
        rationale="Non e possibile preparare un piano senza risorse disponibili.",
        remediation_hint="Verifica assenze e disponibilita in Workforce.",
        source="workforce",
    ),
    _rule(
        "FLEET_AVAILABLE",
        "availability",
        "Almeno un Asset e disponibile.",
        10,
        blocking=True,
        failure_message="Nessun Asset risulta disponibile.",
        rationale="Non e possibile preparare un piano senza Asset disponibili.",
        remediation_hint="Verifica disponibilita e officina in Fleet.",
        source="fleet",
    ),
    _rule(
        "WORKFORCE_CAPABILITIES",
        "capability",
        "Capability Workforce presenti.",
        5,
        blocking=False,
        failure_message="Le capability Workforce sono incomplete.",
        rationale="Le capability migliorano la qualita delle future assegnazioni.",
        remediation_hint="Completa le capability delle Human Resource.",
        source="workforce",
    ),
    _rule(
        "FLEET_CAPABILITIES",
        "capability",
        "Capability Fleet presenti.",
        5,
        blocking=False,
        failure_message="Le capability Fleet sono incomplete.",
        rationale="Le capability descrivono i vincoli operativi degli Asset.",
        remediation_hint="Completa le capability degli Asset.",
        source="fleet",
    ),
    _rule(
        "NO_BLOCKING_VALIDATION_ERRORS",
        "validation",
        "Nessun errore di validazione bloccante.",
        6,
        blocking=True,
        failure_message="Sono presenti errori di validazione bloccanti.",
        rationale="Gli errori bloccanti rendono gli input non affidabili.",
        remediation_hint="Correggi gli errori indicati e rigenera gli snapshot.",
    ),
    _rule(
        "FINGERPRINT_VERSION_COHERENT",
        "integrity",
        "Fingerprint e versioni coerenti.",
        3,
        blocking=True,
        failure_message="Fingerprint o versioni degli input non sono coerenti.",
        rationale="L'integrita dei contratti deve essere verificabile.",
        remediation_hint="Rigenera gli input dalle sorgenti correnti.",
    ),
    _rule(
        "DEPENDENCIES_AVAILABLE",
        "dependency",
        "Dipendenze obbligatorie disponibili.",
        3,
        blocking=True,
        failure_message="Una dipendenza obbligatoria non e disponibile.",
        rationale="La readiness non puo ignorare dipendenze dichiarate.",
        remediation_hint="Ripristina le dipendenze richieste e riprova.",
    ),
)


def _payload(report, input_name: str):
    snapshot = getattr(report, input_name)
    return snapshot.contract.payload if snapshot is not None else None


def _scope_match(report, attribute: str) -> bool | None:
    if report.workforce is None or report.fleet is None:
        return None
    workforce_scope = report.workforce.contract.metadata.scope
    fleet_scope = report.fleet.contract.metadata.scope
    if attribute == "operational_unit":
        expected = report.expected_operational_unit.external_identifier
        values = {
            workforce_scope.operational_unit.external_identifier,
            fleet_scope.operational_unit.external_identifier,
            expected,
        }
    else:
        values = {
            workforce_scope.operation_date,
            fleet_scope.operation_date,
            report.expected_planning_date,
        }
    return len(values) == 1


def _fresh(report, input_name: str) -> bool | None:
    snapshot = getattr(report, input_name)
    if snapshot is None:
        return None
    metadata = snapshot.contract.metadata
    return (
        snapshot.validation.status is not PlanningInputStatus.STALE
        and report.evaluated_at <= metadata.freshness.expires_at
    )


def _not_partial(report, input_name: str) -> bool | None:
    snapshot = getattr(report, input_name)
    if snapshot is None:
        return None
    return snapshot.validation.status is not PlanningInputStatus.PARTIAL


def _available(report, input_name: str) -> bool | None:
    payload = _payload(report, input_name)
    if payload is None:
        return None
    return any(item.available for item in payload.availability)


def _capabilities(report, input_name: str) -> bool | None:
    payload = _payload(report, input_name)
    if payload is None:
        return None
    if isinstance(payload, WorkforcePlanningInput):
        resources_present = bool(payload.human_resources)
    elif isinstance(payload, FleetPlanningInput):
        resources_present = bool(payload.registry.assets)
    else:
        return False
    return bool(payload.capabilities) if resources_present else None


def _no_blocking_validation_errors(
    report: PlanningReadinessEvaluationReport,
) -> bool | None:
    snapshots = tuple(
        item for item in (report.workforce, report.fleet) if item is not None
    )
    if not snapshots:
        return None
    return not any(
        issue.blocking
        for snapshot in snapshots
        for issue in snapshot.validation.issues
    )


def _fingerprints_coherent(
    report: PlanningReadinessEvaluationReport,
) -> bool | None:
    snapshots = tuple(
        item for item in (report.workforce, report.fleet) if item is not None
    )
    if len(snapshots) != 2:
        return None
    for snapshot in snapshots:
        metadata = snapshot.contract.metadata
        expected = planning_input_fingerprint(
            metadata.scope,
            snapshot.contract.payload,
        )
        if (
            snapshot.contract.contract_version
            != PLANNING_INPUT_CONTRACT_VERSION
            or metadata.source.contract_version
            != PLANNING_INPUT_CONTRACT_VERSION
            or metadata.version.value != expected
            or not metadata.source.source_reference.endswith(expected)
        ):
            return False
    if report.envelope is None:
        return True
    expected_envelope = planning_input_envelope_fingerprint(
        report.envelope.scope,
        report.envelope.snapshots,
    )
    return (
        report.envelope.contract_version == PLANNING_INPUT_CONTRACT_VERSION
        and report.envelope.version.value == expected_envelope
    )


def _required_dependencies_available(
    report: PlanningReadinessEvaluationReport,
) -> bool | None:
    snapshots = tuple(
        item for item in (report.workforce, report.fleet) if item is not None
    )
    if not snapshots:
        return None
    dependencies = tuple(
        dependency
        for snapshot in snapshots
        for dependency in snapshot.contract.dependencies
    )
    return all(
        dependency.satisfied
        for dependency in dependencies
        if dependency.required
    )


RuleEvaluator = Callable[[PlanningReadinessEvaluationReport], bool | None]


_RULE_EVALUATORS: dict[str, RuleEvaluator] = {
    "ENVELOPE_PRESENT": lambda report: report.envelope is not None,
    "ENVELOPE_VALIDATED": lambda report: (
        None
        if report.envelope is None
        else all(
            item.status is PlanningInputStatus.READY
            for item in report.envelope.validation
        )
    ),
    "RUNTIME_COMPATIBLE": lambda report: (
        report.runtime_status.casefold() != "incompatible"
    ),
    "WORKFORCE_PRESENT": lambda report: report.workforce is not None,
    "FLEET_PRESENT": lambda report: report.fleet is not None,
    "OPERATIONAL_UNIT_MATCH": lambda report: _scope_match(
        report, "operational_unit"
    ),
    "PLANNING_DATE_MATCH": lambda report: _scope_match(
        report, "planning_date"
    ),
    "WORKFORCE_FRESH": lambda report: _fresh(report, "workforce"),
    "FLEET_FRESH": lambda report: _fresh(report, "fleet"),
    "WORKFORCE_COMPLETE": lambda report: _not_partial(
        report, "workforce"
    ),
    "FLEET_COMPLETE": lambda report: _not_partial(report, "fleet"),
    "WORKFORCE_AVAILABLE": lambda report: _available(report, "workforce"),
    "FLEET_AVAILABLE": lambda report: _available(report, "fleet"),
    "WORKFORCE_CAPABILITIES": lambda report: _capabilities(
        report, "workforce"
    ),
    "FLEET_CAPABILITIES": lambda report: _capabilities(report, "fleet"),
    "NO_BLOCKING_VALIDATION_ERRORS": _no_blocking_validation_errors,
    "FINGERPRINT_VERSION_COHERENT": _fingerprints_coherent,
    "DEPENDENCIES_AVAILABLE": _required_dependencies_available,
}


def evaluate_planning_readiness_rules(
    report: PlanningReadinessEvaluationReport,
) -> tuple[PlanningReadinessRuleResult, ...]:
    results = []
    for rule in PLANNING_READINESS_RULES:
        passed = _RULE_EVALUATORS[rule.code](report)
        if passed is True:
            message = rule.description
            severity = PlanningReadinessSeverity.INFO
        elif passed is False:
            message = rule.failure_message
            severity = (
                PlanningReadinessSeverity.CRITICAL
                if rule.blocking
                else PlanningReadinessSeverity.WARNING
            )
        else:
            message = f"{rule.description} non valutabile."
            severity = PlanningReadinessSeverity.INFO
        results.append(
            PlanningReadinessRuleResult(
                code=rule.code,
                category=rule.category,
                passed=passed,
                weight=rule.weight,
                score_awarded=rule.weight if passed is True else 0,
                blocking=rule.blocking,
                message=message,
                source=rule.source,
                severity=severity,
            )
        )
    return tuple(results)


def readiness_rule(code: str) -> PlanningReadinessRule:
    return next(rule for rule in PLANNING_READINESS_RULES if rule.code == code)


assert sum(rule.weight for rule in PLANNING_READINESS_RULES) == 100
