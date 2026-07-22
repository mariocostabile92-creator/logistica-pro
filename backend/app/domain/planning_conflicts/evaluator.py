from app.domain.planning_conflicts.formatter import PlanningConflictFormatter
from app.domain.planning_conflicts.models import (
    PlanningConflict,
    PlanningConflictDiagnostic,
)
from app.domain.planning_inputs import (
    FleetPlanningInput,
    PlanningInputEnvelope,
    WorkforcePlanningInput,
)
from app.domain.planning_readiness import PlanningReadinessResult


_CODE_ALIASES = {
    "WORKFORCE_PRESENT": "WORKFORCE_MISSING",
    "WORKFORCE_INPUT_MISSING": "WORKFORCE_MISSING",
    "FLEET_PRESENT": "FLEET_MISSING",
    "FLEET_INPUT_MISSING": "FLEET_MISSING",
    "OPERATIONAL_UNIT_MATCH": "OPERATIONAL_UNIT_MISMATCH",
    "OPERATIONAL_UNIT": "OPERATIONAL_UNIT_MISMATCH",
    "ORGANIZATION": "OPERATIONAL_UNIT_MISMATCH",
    "REQUESTED_SCOPE": "OPERATIONAL_UNIT_MISMATCH",
    "PLANNING_DATE_MATCH": "PLANNING_DATE_MISMATCH",
    "PLANNING_DATE": "PLANNING_DATE_MISMATCH",
    "WORKFORCE_FRESH": "WORKFORCE_SNAPSHOT_STALE",
    "FLEET_FRESH": "FLEET_SNAPSHOT_STALE",
    "WORKFORCE_CAPABILITIES": "WORKFORCE_CAPABILITIES_MISSING",
    "FLEET_CAPABILITIES": "FLEET_CAPABILITIES_MISSING",
    "WORKFORCE_AVAILABLE": "ZERO_WORKFORCE_AVAILABLE",
    "FLEET_AVAILABLE": "ZERO_FLEET_AVAILABLE",
    "VERSION": "VERSION_MISMATCH",
    "FINGERPRINT": "FINGERPRINT_MISMATCH",
    "RUNTIME_COMPATIBLE": "RUNTIME_INCOMPATIBLE",
    "ENVELOPE_PRESENT": "ENVELOPE_INCOMPLETE",
    "ENVELOPE_VALIDATED": "ENVELOPE_INCOMPLETE",
    "DEPENDENCIES_AVAILABLE": "DEPENDENCY_MISSING",
    "OPTIONAL_DEPENDENCY_MISSING": "OPTIONAL_DEPENDENCY_MISSING",
    "WORKFORCE_COMPLETE": "SNAPSHOT_PARTIAL",
    "FLEET_COMPLETE": "SNAPSHOT_PARTIAL",
    "SNAPSHOT_EXPIRING_SOON": "SNAPSHOT_EXPIRING_SOON",
    "REDUCED_WORKFORCE_COVERAGE": "WORKFORCE_COVERAGE_REDUCED",
}


def _canonical_code(code: str, category: str, source: str) -> str:
    normalized = code.upper()
    if normalized == "STALE_INPUT":
        prefix = "FLEET" if source.casefold() == "fleet" else "WORKFORCE"
        return f"{prefix}_SNAPSHOT_STALE"
    if normalized.startswith("RUNTIME_ERROR_"):
        return "RUNTIME_INCOMPATIBLE"
    if normalized.startswith("LEGACY_"):
        return "LEGACY_CONTRACT"
    if normalized in _CODE_ALIASES:
        return _CODE_ALIASES[normalized]
    if category.casefold() == "validation":
        return normalized
    return normalized


def _snapshot(envelope: PlanningInputEnvelope | None, source: str):
    if envelope is None:
        return None
    source_name = source.casefold()
    for snapshot in envelope.snapshots:
        if snapshot.contract.metadata.input_type.value == source_name:
            return snapshot
    return None


def _limited(values) -> tuple[str, ...]:
    return tuple(sorted(dict.fromkeys(values)))[:10]


def _affected_entities(
    code: str,
    source: str,
    envelope: PlanningInputEnvelope | None,
) -> tuple[str, ...]:
    snapshot = _snapshot(envelope, source)
    if snapshot is None:
        return ()
    payload = snapshot.contract.payload
    if code == "WORKFORCE_CAPABILITIES_MISSING" and isinstance(
        payload, WorkforcePlanningInput
    ):
        capable = {item.resource_identifier for item in payload.capabilities}
        return _limited(
            item.external_identifier
            for item in payload.human_resources
            if item.external_identifier not in capable
        )
    if code == "FLEET_CAPABILITIES_MISSING" and isinstance(
        payload, FleetPlanningInput
    ):
        capable = {item.resource_identifier for item in payload.capabilities}
        return _limited(
            item.external_identifier
            for item in payload.registry.assets
            if item.external_identifier not in capable
        )
    if code in {"ZERO_WORKFORCE_AVAILABLE", "ZERO_FLEET_AVAILABLE"}:
        return _limited(item.resource_identifier for item in payload.availability)
    if code in {"DEPENDENCY_MISSING", "OPTIONAL_DEPENDENCY_MISSING"}:
        return _limited(
            item.dependency_id
            for item in snapshot.contract.dependencies
            if not item.satisfied
        )
    return (snapshot.snapshot_id,)


class PlanningConflictEvaluator:
    def __init__(self, formatter: PlanningConflictFormatter) -> None:
        self._formatter = formatter

    def evaluate(
        self,
        readiness: PlanningReadinessResult,
        envelope: PlanningInputEnvelope | None,
    ) -> tuple[PlanningConflict, ...]:
        issue_records = (
            *((item, True) for item in readiness.blockers),
            *((item, True) for item in readiness.missing_inputs),
            *((item, False) for item in readiness.warnings),
            *((item, item.severity.value == "critical") for item in readiness.diagnostics),
        )
        issues = tuple(item for item, _ in issue_records)
        exact_codes = {item.code.upper() for item in issues}
        conflicts: dict[tuple[str, str], PlanningConflict] = {}
        singleton_codes = {
            "OPERATIONAL_UNIT_MISMATCH",
            "PLANNING_DATE_MISMATCH",
            "VERSION_MISMATCH",
            "FINGERPRINT_MISMATCH",
            "RUNTIME_INCOMPATIBLE",
            "ENVELOPE_INCOMPLETE",
        }
        for issue, explicit_blocking in issue_records:
            raw_code = issue.code.upper()
            if raw_code == "FINGERPRINT_VERSION_COHERENT" and (
                {"VERSION", "FINGERPRINT"} & exact_codes
            ):
                continue
            if raw_code == "NO_BLOCKING_VALIDATION_ERRORS" and any(
                item.category.casefold() == "validation"
                and item.code.upper() != raw_code
                for item in issues
            ):
                continue
            source = issue.source.casefold()
            code = _canonical_code(issue.code, issue.category, source)
            key = (code, "*") if code in singleton_codes else (code, source)
            if key in conflicts:
                continue
            diagnostic = PlanningConflictDiagnostic(
                code=issue.code,
                message=issue.message,
                source=source,
                details=tuple(
                    value
                    for value in (
                        getattr(issue, "rationale", None),
                        getattr(issue, "remediation_hint", None),
                    )
                    if value
                ),
            )
            conflicts[key] = self._formatter.format(
                code=code,
                source=source,
                blocking=explicit_blocking,
                diagnostic=diagnostic,
                readiness=readiness,
                affected_entities=_affected_entities(code, source, envelope),
            )
        return tuple(conflicts.values())
