import ast
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from app.domain.core_language import OperationalUnit
from app.domain.planning_inputs import (
    PlanningInputStatus,
    PlanningInputVersion,
)
from app.plugins.fleet.application import planning_input_producer as fleet_inputs
from app.plugins.fleet.domain.models import Asset
from app.plugins.workforce.application import (
    planning_input_producer as workforce_inputs,
)
from app.plugins.workforce.domain.models import (
    WorkforceDayStatus,
    WorkforceMember,
    WorkforceRequirement,
    WorkforceValueOrigin,
)
from app.runtime.planning_inputs import (
    PlanningInputRuntimeService,
    PlanningInputRuntimeStatus,
)


APP_DIR = Path(__file__).parents[1] / "app"
NOW = datetime(2026, 7, 22, 7, 0, tzinfo=UTC)
RECENT = datetime(2026, 7, 22, 6, 45, tzinfo=UTC)
OLD = datetime(2026, 7, 22, 4, 0, tzinfo=UTC)
OPERATION_DATE = date(2026, 7, 22)
UNIT = OperationalUnit(external_identifier="unit-a", name="Unit A")
TTL = timedelta(hours=1)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _member(
    member_id: int,
    external_identifier: str | None = None,
    *,
    updated_at: datetime = RECENT,
) -> WorkforceMember:
    return WorkforceMember(
        workforce_member_id=member_id,
        external_identifier=(
            external_identifier or f"human-{member_id:03d}"
        ),
        display_name=f"Resource {member_id}",
        role="courier",
        capabilities=["license-b"],
        source_reference=f"synthetic:{member_id}",
        created_at=_iso(updated_at),
        updated_at=_iso(updated_at),
    )


def _status(
    status_id: int,
    member_id: int,
    *,
    updated_at: datetime = RECENT,
) -> WorkforceDayStatus:
    return WorkforceDayStatus(
        status_id=status_id,
        workforce_member_id=member_id,
        date=OPERATION_DATE.isoformat(),
        status_code="scheduled",
        availability=True,
        shift_code="morning",
        start_time="07:00",
        end_time="15:00",
        source_reference=f"synthetic:{status_id}",
        observed_or_confirmed=WorkforceValueOrigin.IMPORTED,
        updated_at=_iso(updated_at),
    )


def _requirement() -> WorkforceRequirement:
    return WorkforceRequirement(
        requirement_id=1,
        date=OPERATION_DATE.isoformat(),
        operational_unit_id=UNIT.external_identifier,
        required_resources=1,
        required_capabilities=["license-b"],
        source="synthetic",
        version=1,
    )


def _asset(
    asset_id: int = 1,
    *,
    updated_at: datetime = RECENT,
) -> Asset:
    return Asset(
        id=asset_id,
        external_identifier=f"asset-{asset_id:03d}",
        plate=f"QA{asset_id:05d}",
        category="van",
        status="active",
        availability="available",
        capabilities=["electric"],
        created_at=_iso(updated_at),
        updated_at=_iso(updated_at),
    )


def _workforce_producer(
    *,
    members=None,
    statuses=None,
    requirements=None,
    force_unit: OperationalUnit | None = None,
    transform=None,
):
    workforce_members = [_member(1)] if members is None else members
    workforce_statuses = [_status(1, 1)] if statuses is None else statuses
    workforce_requirements = (
        [_requirement()] if requirements is None else requirements
    )

    def produce(**request):
        snapshot = workforce_inputs.build_workforce_planning_input_snapshot(
            organization_id=request["organization_id"],
            operational_unit=force_unit or request["operational_unit"],
            operation_date=request["operation_date"],
            members=workforce_members,
            statuses=workforce_statuses,
            requirements=workforce_requirements,
            assessed_at=request["assessed_at"],
            freshness_ttl=request["freshness_ttl"],
        )
        return transform(snapshot) if transform else snapshot

    return produce


def _fleet_producer(
    *,
    assets=None,
    force_unit: OperationalUnit | None = None,
    force_date: date | None = None,
    transform=None,
):
    fleet_assets = [_asset()] if assets is None else assets

    def produce(**request):
        snapshot = fleet_inputs.build_fleet_planning_input_snapshot(
            organization_id=request["organization_id"],
            operational_unit=force_unit or request["operational_unit"],
            operation_date=force_date or request["operation_date"],
            assets=fleet_assets,
            assessed_at=request["assessed_at"],
            freshness_ttl=request["freshness_ttl"],
        )
        return transform(snapshot) if transform else snapshot

    return produce


def _service(
    workforce=None,
    fleet=None,
    *,
    workforce_ttl: timedelta = TTL,
    fleet_ttl: timedelta = TTL,
) -> PlanningInputRuntimeService:
    return PlanningInputRuntimeService(
        workforce_producer=workforce or _workforce_producer(),
        fleet_producer=fleet or _fleet_producer(),
        workforce_freshness_ttl=workforce_ttl,
        fleet_freshness_ttl=fleet_ttl,
    )


def _compose(service: PlanningInputRuntimeService):
    return service.compose(
        organization_id="organization-one",
        operational_unit=UNIT,
        operation_date=OPERATION_DATE,
        composed_at=NOW,
    )


def _replace_contract_version(snapshot, version: str):
    source = snapshot.contract.metadata.source.model_copy(
        update={"contract_version": version}
    )
    metadata = snapshot.contract.metadata.model_copy(
        update={"source": source}
    )
    contract = snapshot.contract.model_copy(
        update={"contract_version": version, "metadata": metadata}
    )
    return snapshot.model_copy(update={"contract": contract})


def _replace_fingerprint(snapshot, value: str):
    metadata = snapshot.contract.metadata.model_copy(
        update={"version": PlanningInputVersion(value=value)}
    )
    contract = snapshot.contract.model_copy(update={"metadata": metadata})
    return snapshot.model_copy(update={"contract": contract})


def _replace_source_time(snapshot, produced_at: datetime):
    source = snapshot.contract.metadata.source.model_copy(
        update={"produced_at": produced_at}
    )
    metadata = snapshot.contract.metadata.model_copy(
        update={"source": source}
    )
    contract = snapshot.contract.model_copy(update={"metadata": metadata})
    return snapshot.model_copy(update={"contract": contract})


def _check(result, code: str):
    return next(
        item for item in result.compatibility.checks if item.code == code
    )


def test_ready_runtime_builds_a_complete_envelope_from_real_producers():
    result = _compose(_service())

    assert result.status is PlanningInputRuntimeStatus.READY
    assert result.compatibility.compatible is True
    assert result.envelope is not None
    assert result.envelope.operational_unit == UNIT
    assert result.envelope.planning_date == OPERATION_DATE
    assert result.envelope.fingerprint == result.envelope.version.value
    assert len(result.envelope.snapshots) == 2
    assert len(result.envelope.freshness) == 2
    assert len(result.envelope.validation) == 2
    assert len(result.envelope.metadata) == 2
    assert all(
        validation.status is PlanningInputStatus.READY
        for validation in result.envelope.validation
    )


def test_partial_runtime_reports_workforce_limitation_without_envelope():
    result = _compose(
        _service(workforce=_workforce_producer(requirements=[]))
    )

    assert result.status is PlanningInputRuntimeStatus.PARTIAL
    assert result.envelope is None
    assert "Workforce partial." in result.diagnostics.warnings


def test_stale_runtime_reports_expired_inputs():
    result = _compose(
        _service(
            workforce=_workforce_producer(
                members=[_member(1, updated_at=OLD)],
                statuses=[_status(1, 1, updated_at=OLD)],
            ),
            fleet=_fleet_producer(assets=[_asset(updated_at=OLD)]),
        )
    )

    assert result.status is PlanningInputRuntimeStatus.STALE
    assert "Workforce stale." in result.diagnostics.warnings
    assert "Fleet stale." in result.diagnostics.warnings


def test_invalid_runtime_reports_invalid_workforce_snapshot():
    result = _compose(
        _service(
            workforce=_workforce_producer(
                members=[_member(1, "duplicate"), _member(2, "duplicate")],
                statuses=[_status(1, 1), _status(2, 2)],
            )
        )
    )

    assert result.status is PlanningInputRuntimeStatus.INVALID
    assert "Workforce invalid." in result.diagnostics.errors


def test_missing_runtime_propagates_a_missing_workforce_contract():
    result = _compose(
        _service(
            workforce=_workforce_producer(
                members=[], statuses=[], requirements=[]
            )
        )
    )

    assert result.status is PlanningInputRuntimeStatus.MISSING
    assert result.report.workforce.validation.status is PlanningInputStatus.MISSING


@pytest.mark.parametrize(
    ("workforce", "fleet", "expected_error"),
    (
        (lambda **_: None, _fleet_producer(), "Workforce input is missing."),
        (_workforce_producer(), lambda **_: None, "Fleet input is missing."),
    ),
)
def test_absent_workforce_or_fleet_is_incompatible(
    workforce,
    fleet,
    expected_error,
):
    result = _compose(_service(workforce=workforce, fleet=fleet))

    assert result.status is PlanningInputRuntimeStatus.INCOMPATIBLE
    assert expected_error in result.diagnostics.errors
    assert result.envelope is None


def test_operational_unit_mismatch_is_explicitly_incompatible():
    other_unit = OperationalUnit(external_identifier="unit-b", name="Unit B")
    result = _compose(
        _service(fleet=_fleet_producer(force_unit=other_unit))
    )

    assert result.status is PlanningInputRuntimeStatus.INCOMPATIBLE
    assert _check(result, "OPERATIONAL_UNIT").compatible is False
    assert "Operational Unit mismatch" in _check(
        result, "OPERATIONAL_UNIT"
    ).message


def test_planning_date_mismatch_is_explicitly_incompatible():
    result = _compose(
        _service(
            fleet=_fleet_producer(
                force_date=OPERATION_DATE + timedelta(days=1)
            )
        )
    )

    assert result.status is PlanningInputRuntimeStatus.INCOMPATIBLE
    assert _check(result, "PLANNING_DATE").compatible is False
    assert "Planning date mismatch" in _check(
        result, "PLANNING_DATE"
    ).message


def test_version_mismatch_is_explicitly_incompatible():
    result = _compose(
        _service(
            fleet=_fleet_producer(
                transform=lambda snapshot: _replace_contract_version(
                    snapshot, "2.0"
                )
            )
        )
    )

    assert result.status is PlanningInputRuntimeStatus.INCOMPATIBLE
    assert _check(result, "VERSION").compatible is False
    assert any(
        "Version mismatch" in error for error in result.diagnostics.errors
    )


def test_non_overlapping_freshness_is_explicitly_incompatible():
    result = _compose(
        _service(
            workforce=_workforce_producer(
                members=[_member(1, updated_at=OLD)],
                statuses=[_status(1, 1, updated_at=OLD)],
            ),
            fleet=_fleet_producer(),
        )
    )

    assert result.status is PlanningInputRuntimeStatus.INCOMPATIBLE
    assert _check(result, "FRESHNESS").compatible is False
    assert any(
        "Freshness mismatch" in error for error in result.diagnostics.errors
    )


def test_fingerprint_mismatch_is_explicitly_incompatible():
    result = _compose(
        _service(
            fleet=_fleet_producer(
                transform=lambda snapshot: _replace_fingerprint(
                    snapshot, "tampered"
                )
            )
        )
    )

    assert result.status is PlanningInputRuntimeStatus.INCOMPATIBLE
    assert _check(result, "FINGERPRINT").compatible is False
    assert any(
        "Fingerprint mismatch" in error for error in result.diagnostics.errors
    )


def test_source_mismatch_is_explicitly_incompatible():
    result = _compose(
        _service(
            fleet=_fleet_producer(
                transform=lambda snapshot: _replace_source_time(snapshot, OLD)
            )
        )
    )

    assert result.status is PlanningInputRuntimeStatus.INCOMPATIBLE
    assert _check(result, "SOURCE").compatible is False
    assert any("Source mismatch" in error for error in result.diagnostics.errors)


def test_composition_report_contains_inputs_checks_and_timestamp():
    result = _compose(_service())
    report = result.report

    assert report.workforce is not None
    assert report.fleet is not None
    assert report.timestamp == NOW
    assert report.status is PlanningInputRuntimeStatus.READY
    assert {check.code for check in report.compatibility.checks} >= {
        "OPERATIONAL_UNIT",
        "PLANNING_DATE",
        "VERSION",
        "FRESHNESS",
        "VALIDATION",
        "SOURCE",
        "FINGERPRINT",
    }
    assert report.diagnostics.warnings == ()
    assert report.diagnostics.errors == ()


def test_runtime_declares_legacy_flow_active():
    result = _compose(_service())

    assert result.legacy_flow_active is True
    assert result.report.legacy_flow_active is True


def test_producer_failure_is_sanitized_in_runtime_diagnostics():
    def failing_workforce(**_):
        raise RuntimeError("private stack detail")

    result = _compose(_service(workforce=failing_workforce))

    assert result.status is PlanningInputRuntimeStatus.INCOMPATIBLE
    assert "Workforce producer failed." in result.diagnostics.errors
    assert "private stack detail" not in repr(result.diagnostics)


def test_runtime_layer_has_no_infrastructure_dependencies():
    forbidden = (
        "app.adapters",
        "app.api",
        "app.importers",
        "app.plugins",
        "app.repositories",
        "app.services",
    )
    violations = []
    for path in (APP_DIR / "runtime" / "planning_inputs").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            module = None
            if isinstance(node, ast.ImportFrom):
                module = node.module
            elif isinstance(node, ast.Import) and node.names:
                module = node.names[0].name
            if module and module.startswith(forbidden):
                violations.append(f"{path.name}: {module}")

    planning_source = (
        APP_DIR / "services" / "planning_generation_service.py"
    ).read_text(encoding="utf-8")

    assert violations == []
    assert "app.runtime.planning_inputs" not in planning_source
    assert "PlanningInputRuntimeService" not in planning_source
