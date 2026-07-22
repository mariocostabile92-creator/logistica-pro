from app.domain.planning_inputs import (
    PLANNING_INPUT_CONTRACT_VERSION,
    PlanningInputScope,
    PlanningInputSnapshot,
    PlanningInputStatus,
    PlanningInputType,
    planning_input_fingerprint,
)
from app.runtime.planning_inputs.models import (
    PlanningInputCompatibility,
    PlanningInputCompatibilityCheck,
)


def _check(
    code: str,
    compatible: bool | None,
    success: str,
    failure: str,
) -> PlanningInputCompatibilityCheck:
    return PlanningInputCompatibilityCheck(
        code=code,
        compatible=compatible,
        message=success if compatible is True else failure,
    )


def _not_evaluable(code: str, subject: str) -> PlanningInputCompatibilityCheck:
    return PlanningInputCompatibilityCheck(
        code=code,
        compatible=None,
        message=f"{subject} cannot be checked because an input is missing.",
    )


def _fingerprint_is_valid(snapshot: PlanningInputSnapshot) -> bool:
    metadata = snapshot.contract.metadata
    expected = planning_input_fingerprint(
        metadata.scope,
        snapshot.contract.payload,
    )
    return (
        metadata.version.value == expected
        and metadata.source.source_reference.endswith(expected)
    )


def evaluate_planning_input_compatibility(
    workforce: PlanningInputSnapshot | None,
    fleet: PlanningInputSnapshot | None,
    expected_scope: PlanningInputScope,
) -> PlanningInputCompatibility:
    checks: list[PlanningInputCompatibilityCheck] = [
        _check(
            "WORKFORCE_PRESENT",
            workforce is not None,
            "Workforce input is present.",
            "Workforce input is missing.",
        ),
        _check(
            "FLEET_PRESENT",
            fleet is not None,
            "Fleet input is present.",
            "Fleet input is missing.",
        ),
    ]
    if workforce is None or fleet is None:
        checks.extend(
            _not_evaluable(code, subject)
            for code, subject in (
                ("INPUT_TYPES", "Input types"),
                ("ORGANIZATION", "Organization"),
                ("OPERATIONAL_UNIT", "Operational Unit"),
                ("PLANNING_DATE", "Planning date"),
                ("REQUESTED_SCOPE", "Requested scope"),
                ("VERSION", "Version"),
                ("FRESHNESS", "Freshness"),
                ("VALIDATION", "Validation"),
                ("SOURCE", "Source"),
                ("FINGERPRINT", "Fingerprint"),
            )
        )
        return PlanningInputCompatibility(compatible=False, checks=tuple(checks))

    workforce_metadata = workforce.contract.metadata
    fleet_metadata = fleet.contract.metadata
    workforce_scope = workforce_metadata.scope
    fleet_scope = fleet_metadata.scope
    input_types_match = (
        workforce_metadata.input_type is PlanningInputType.WORKFORCE
        and fleet_metadata.input_type is PlanningInputType.FLEET
    )
    organization_matches = (
        workforce_scope.organization_id == fleet_scope.organization_id
    )
    unit_matches = (
        workforce_scope.operational_unit.external_identifier
        == fleet_scope.operational_unit.external_identifier
    )
    date_matches = workforce_scope.operation_date == fleet_scope.operation_date
    requested_scope_matches = (
        workforce_scope.identity == expected_scope.identity
        and fleet_scope.identity == expected_scope.identity
    )
    version_matches = (
        workforce.contract.contract_version
        == fleet.contract.contract_version
        == PLANNING_INPUT_CONTRACT_VERSION
        and workforce_metadata.source.contract_version
        == workforce.contract.contract_version
        and fleet_metadata.source.contract_version
        == fleet.contract.contract_version
    )
    latest_observation = max(
        workforce_metadata.freshness.observed_at,
        fleet_metadata.freshness.observed_at,
    )
    earliest_expiry = min(
        workforce_metadata.freshness.expires_at,
        fleet_metadata.freshness.expires_at,
    )
    freshness_matches = latest_observation <= earliest_expiry
    validations_match = (
        workforce.validation.status is PlanningInputStatus.READY
        and fleet.validation.status is PlanningInputStatus.READY
    )
    sources_match = (
        workforce_metadata.source.produced_at
        >= workforce_metadata.freshness.observed_at
        and fleet_metadata.source.produced_at
        >= fleet_metadata.freshness.observed_at
    )
    fingerprints_match = (
        _fingerprint_is_valid(workforce)
        and _fingerprint_is_valid(fleet)
    )
    checks.extend(
        (
            _check(
                "INPUT_TYPES",
                input_types_match,
                "Workforce and Fleet input types are correct.",
                "Workforce or Fleet input type is incorrect.",
            ),
            _check(
                "ORGANIZATION",
                organization_matches,
                "Organization matches across inputs.",
                "Organization mismatch between Workforce and Fleet.",
            ),
            _check(
                "OPERATIONAL_UNIT",
                unit_matches,
                "Operational Unit matches across inputs.",
                "Operational Unit mismatch between Workforce and Fleet.",
            ),
            _check(
                "PLANNING_DATE",
                date_matches,
                "Planning date matches across inputs.",
                "Planning date mismatch between Workforce and Fleet.",
            ),
            _check(
                "REQUESTED_SCOPE",
                requested_scope_matches,
                "Inputs match the requested runtime scope.",
                "Inputs do not match the requested runtime scope.",
            ),
            _check(
                "VERSION",
                version_matches,
                "Contract versions are compatible.",
                "Version mismatch between Planning inputs.",
            ),
            _check(
                "FRESHNESS",
                freshness_matches,
                "Freshness intervals are compatible.",
                "Freshness mismatch between Workforce and Fleet.",
            ),
            _check(
                "VALIDATION",
                validations_match,
                "Both input snapshots are READY.",
                "One or more input snapshots are not READY.",
            ),
            _check(
                "SOURCE",
                sources_match,
                "Input sources are chronologically valid.",
                "Source mismatch in Planning inputs.",
            ),
            _check(
                "FINGERPRINT",
                fingerprints_match,
                "Input fingerprints are valid.",
                "Fingerprint mismatch in Planning inputs.",
            ),
        )
    )
    return PlanningInputCompatibility(
        compatible=all(check.compatible is True for check in checks),
        checks=tuple(checks),
    )
