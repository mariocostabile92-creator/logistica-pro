from datetime import datetime

from app.domain.core_language import ResourceKind
from app.domain.planning_inputs.models import (
    FleetPlanningInput,
    PlanningInputContract,
    PlanningInputSnapshot,
    PlanningInputStatus,
    PlanningInputValidation,
    PlanningInputValidationIssue,
    WorkforcePlanningInput,
)


def _issue(
    code: str,
    message: str,
    field: str | None = None,
    *,
    blocking: bool = False,
) -> PlanningInputValidationIssue:
    return PlanningInputValidationIssue(
        code=code,
        message=message,
        field=field,
        blocking=blocking,
    )


def _duplicate_values(values: list[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _validate_workforce(
    payload: WorkforcePlanningInput,
) -> tuple[list[PlanningInputValidationIssue], bool, bool]:
    issues: list[PlanningInputValidationIssue] = []
    missing = not payload.human_resources
    partial = False
    resource_ids = [item.external_identifier for item in payload.human_resources]
    known_resources = set(resource_ids)

    if missing:
        issues.append(
            _issue(
                "MISSING_HUMAN_RESOURCES",
                "The Workforce input contains no Human Resources.",
                "payload.human_resources",
                blocking=True,
            )
        )
    for duplicate in sorted(_duplicate_values(resource_ids)):
        issues.append(
            _issue(
                "DUPLICATE_HUMAN_RESOURCE",
                f"Human Resource {duplicate} is duplicated.",
                "payload.human_resources",
                blocking=True,
            )
        )

    if known_resources and not payload.availability:
        partial = True
        issues.append(
            _issue(
                "MISSING_WORKFORCE_AVAILABILITY",
                "Workforce availability is not present.",
                "payload.availability",
            )
        )
    if payload.coverage is None:
        partial = True
        issues.append(
            _issue(
                "MISSING_WORKFORCE_COVERAGE",
                "Workforce coverage is not present.",
                "payload.coverage",
            )
        )
    if known_resources and not payload.time_windows:
        partial = True
        issues.append(
            _issue(
                "MISSING_WORKFORCE_TIME_WINDOWS",
                "Workforce Time Windows are not present.",
                "payload.time_windows",
            )
        )

    availability_ids = [
        item.resource_identifier for item in payload.availability
    ]
    for duplicate in sorted(_duplicate_values(availability_ids)):
        issues.append(
            _issue(
                "DUPLICATE_WORKFORCE_AVAILABILITY",
                f"Availability for Human Resource {duplicate} is duplicated.",
                "payload.availability",
                blocking=True,
            )
        )
    for item in payload.availability:
        if item.resource_kind is not ResourceKind.HUMAN_RESOURCE:
            issues.append(
                _issue(
                    "INVALID_WORKFORCE_RESOURCE_KIND",
                    "Workforce availability must reference a Human Resource.",
                    "payload.availability",
                    blocking=True,
                )
            )
        if item.resource_identifier not in known_resources:
            issues.append(
                _issue(
                    "UNKNOWN_HUMAN_RESOURCE",
                    "Workforce availability references an unknown resource.",
                    "payload.availability",
                    blocking=True,
                )
            )

    for item in payload.capabilities:
        if item.resource_kind is not ResourceKind.HUMAN_RESOURCE:
            issues.append(
                _issue(
                    "INVALID_WORKFORCE_CAPABILITY_KIND",
                    "Workforce capability must reference a Human Resource.",
                    "payload.capabilities",
                    blocking=True,
                )
            )
        if item.resource_identifier not in known_resources:
            issues.append(
                _issue(
                    "UNKNOWN_CAPABILITY_HUMAN_RESOURCE",
                    "Workforce capability references an unknown resource.",
                    "payload.capabilities",
                    blocking=True,
                )
            )

    return issues, missing, partial


def _validate_fleet(
    payload: FleetPlanningInput,
) -> tuple[list[PlanningInputValidationIssue], bool, bool]:
    issues: list[PlanningInputValidationIssue] = []
    missing = not payload.registry.assets
    partial = False
    asset_ids = [item.external_identifier for item in payload.registry.assets]
    known_assets = set(asset_ids)

    if missing:
        issues.append(
            _issue(
                "MISSING_ASSET_REGISTRY",
                "The Fleet input contains no Assets.",
                "payload.registry.assets",
                blocking=True,
            )
        )
    for duplicate in sorted(_duplicate_values(asset_ids)):
        issues.append(
            _issue(
                "DUPLICATE_ASSET",
                f"Asset {duplicate} is duplicated.",
                "payload.registry.assets",
                blocking=True,
            )
        )

    if known_assets and not payload.availability:
        partial = True
        issues.append(
            _issue(
                "MISSING_FLEET_AVAILABILITY",
                "Fleet availability is not present.",
                "payload.availability",
            )
        )

    availability_ids = [
        item.resource_identifier for item in payload.availability
    ]
    for duplicate in sorted(_duplicate_values(availability_ids)):
        issues.append(
            _issue(
                "DUPLICATE_FLEET_AVAILABILITY",
                f"Availability for Asset {duplicate} is duplicated.",
                "payload.availability",
                blocking=True,
            )
        )
    for item in payload.availability:
        if item.resource_kind is not ResourceKind.ASSET:
            issues.append(
                _issue(
                    "INVALID_FLEET_RESOURCE_KIND",
                    "Fleet availability must reference an Asset.",
                    "payload.availability",
                    blocking=True,
                )
            )
        if item.resource_identifier not in known_assets:
            issues.append(
                _issue(
                    "UNKNOWN_ASSET",
                    "Fleet availability references an unknown Asset.",
                    "payload.availability",
                    blocking=True,
                )
            )

    for item in payload.capabilities:
        if item.resource_kind is not ResourceKind.ASSET:
            issues.append(
                _issue(
                    "INVALID_FLEET_CAPABILITY_KIND",
                    "Fleet capability must reference an Asset.",
                    "payload.capabilities",
                    blocking=True,
                )
            )
        if item.resource_identifier not in known_assets:
            issues.append(
                _issue(
                    "UNKNOWN_CAPABILITY_ASSET",
                    "Fleet capability references an unknown Asset.",
                    "payload.capabilities",
                    blocking=True,
                )
            )

    return issues, missing, partial


def validate_planning_input(
    contract: PlanningInputContract,
    assessed_at: datetime,
) -> PlanningInputValidation:
    issues: list[PlanningInputValidationIssue] = []
    missing = False
    partial = False
    source = contract.metadata.source
    freshness = contract.metadata.freshness

    if assessed_at.utcoffset() is None:
        raise ValueError("assessed_at must be timezone-aware.")
    if source.produced_at > assessed_at:
        issues.append(
            _issue(
                "FUTURE_PRODUCTION_TIME",
                "The input was produced after the assessment time.",
                "metadata.source.produced_at",
                blocking=True,
            )
        )
    if freshness.observed_at > source.produced_at:
        issues.append(
            _issue(
                "OBSERVATION_AFTER_PRODUCTION",
                "The observed state is newer than its production time.",
                "metadata.freshness.observed_at",
                blocking=True,
            )
        )

    if isinstance(contract.payload, WorkforcePlanningInput):
        payload_issues, missing, partial = _validate_workforce(
            contract.payload
        )
    else:
        payload_issues, missing, partial = _validate_fleet(contract.payload)
    issues.extend(payload_issues)

    for dependency in contract.dependencies:
        if dependency.satisfied:
            continue
        issues.append(
            _issue(
                "MISSING_REQUIRED_DEPENDENCY"
                if dependency.required
                else "MISSING_OPTIONAL_DEPENDENCY",
                f"Dependency {dependency.dependency_id} is not satisfied.",
                "dependencies",
                blocking=dependency.required,
            )
        )
        missing = missing or dependency.required
        partial = partial or not dependency.required

    invalid = any(
        item.blocking
        and item.code
        not in {
            "MISSING_ASSET_REGISTRY",
            "MISSING_HUMAN_RESOURCES",
            "MISSING_REQUIRED_DEPENDENCY",
        }
        for item in issues
    )
    stale = assessed_at > freshness.expires_at
    if stale:
        issues.append(
            _issue(
                "STALE_INPUT",
                "The input freshness interval has expired.",
                "metadata.freshness.expires_at",
            )
        )

    if invalid:
        status = PlanningInputStatus.INVALID
    elif missing:
        status = PlanningInputStatus.MISSING
    elif stale:
        status = PlanningInputStatus.STALE
    elif partial:
        status = PlanningInputStatus.PARTIAL
    else:
        status = PlanningInputStatus.READY

    return PlanningInputValidation(
        status=status,
        assessed_at=assessed_at,
        issues=tuple(issues),
    )


def create_planning_input_snapshot(
    contract: PlanningInputContract,
    assessed_at: datetime,
    snapshot_id: str | None = None,
) -> PlanningInputSnapshot:
    return PlanningInputSnapshot(
        snapshot_id=snapshot_id or contract.metadata.source.source_reference,
        contract=contract,
        validation=validate_planning_input(contract, assessed_at),
    )
