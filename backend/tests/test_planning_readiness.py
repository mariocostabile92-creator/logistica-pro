import ast
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.domain.core_language import OperationalUnit
from app.domain.planning_inputs import PlanningInputVersion
from app.domain.planning_readiness import (
    PLANNING_READINESS_RULES,
    PlanningReadinessEvaluator,
    PlanningReadinessStatus,
)
from app.main import app
from app.plugins.fleet.application.planning_input_producer import (
    build_fleet_planning_input_snapshot,
)
from app.plugins.fleet.domain.models import Asset
from app.plugins.workforce.application.planning_input_producer import (
    build_workforce_planning_input_snapshot,
)
from app.plugins.workforce.domain.models import (
    WorkforceDayStatus,
    WorkforceMember,
    WorkforceRequirement,
    WorkforceValueOrigin,
)
from app.runtime.planning_inputs import PlanningInputRuntimeService
from app.runtime.planning_readiness import PlanningReadinessService


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
    capabilities: list[str] | None = None,
    updated_at: datetime = RECENT,
) -> WorkforceMember:
    return WorkforceMember(
        workforce_member_id=member_id,
        external_identifier=external_identifier or f"human-{member_id:03d}",
        display_name=f"Resource {member_id}",
        role="courier",
        capabilities=(
            ["license-b"] if capabilities is None else capabilities
        ),
        source_reference=f"synthetic:{member_id}",
        created_at=_iso(updated_at),
        updated_at=_iso(updated_at),
    )


def _status(
    status_id: int,
    member_id: int,
    *,
    available: bool = True,
    updated_at: datetime = RECENT,
) -> WorkforceDayStatus:
    return WorkforceDayStatus(
        status_id=status_id,
        workforce_member_id=member_id,
        date=OPERATION_DATE.isoformat(),
        status_code="scheduled" if available else "unavailable",
        availability=available,
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
    availability: str = "available",
    capabilities: list[str] | None = None,
    updated_at: datetime = RECENT,
) -> Asset:
    return Asset(
        id=asset_id,
        external_identifier=f"asset-{asset_id:03d}",
        plate=f"QA{asset_id:05d}",
        category="van",
        status="active",
        availability=availability,
        capabilities=(["electric"] if capabilities is None else capabilities),
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
    values = [_member(1)] if members is None else members
    daily = [_status(1, 1)] if statuses is None else statuses
    required = [_requirement()] if requirements is None else requirements

    def produce(**request):
        snapshot = build_workforce_planning_input_snapshot(
            organization_id=request["organization_id"],
            operational_unit=force_unit or request["operational_unit"],
            operation_date=request["operation_date"],
            members=values,
            statuses=daily,
            requirements=required,
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
    values = [_asset()] if assets is None else assets

    def produce(**request):
        snapshot = build_fleet_planning_input_snapshot(
            organization_id=request["organization_id"],
            operational_unit=force_unit or request["operational_unit"],
            operation_date=force_date or request["operation_date"],
            assets=values,
            assessed_at=request["assessed_at"],
            freshness_ttl=request["freshness_ttl"],
        )
        return transform(snapshot) if transform else snapshot

    return produce


def _replace_fingerprint(snapshot, value: str):
    metadata = snapshot.contract.metadata.model_copy(
        update={"version": PlanningInputVersion(value=value)}
    )
    contract = snapshot.contract.model_copy(update={"metadata": metadata})
    return snapshot.model_copy(update={"contract": contract})


def _replace_contract_version(snapshot, value: str):
    source = snapshot.contract.metadata.source.model_copy(
        update={"contract_version": value}
    )
    metadata = snapshot.contract.metadata.model_copy(update={"source": source})
    contract = snapshot.contract.model_copy(
        update={"contract_version": value, "metadata": metadata}
    )
    return snapshot.model_copy(update={"contract": contract})


def _service(workforce=None, fleet=None):
    runtime = PlanningInputRuntimeService(
        workforce_producer=workforce or _workforce_producer(),
        fleet_producer=fleet or _fleet_producer(),
        workforce_freshness_ttl=TTL,
        fleet_freshness_ttl=TTL,
    )
    return PlanningReadinessService(
        composition_provider=runtime,
        evaluator=PlanningReadinessEvaluator(),
    )


def _evaluate(service=None):
    return (service or _service()).evaluate(
        organization_id="organization-one",
        operational_unit=UNIT,
        operation_date=OPERATION_DATE,
        evaluated_at=NOW,
    )


def _codes(items):
    return {item.code for item in items}


def test_complete_inputs_are_ready_with_a_perfect_explainable_score():
    result = _evaluate()

    assert result.status is PlanningReadinessStatus.READY
    assert result.is_ready is True
    assert result.score.value == 100
    assert len(result.rule_results) == 18
    assert sum(rule.weight for rule in PLANNING_READINESS_RULES) == 100
    assert result.blockers == ()


def test_ready_inputs_with_incomplete_capabilities_return_non_blocking_warning():
    result = _evaluate(
        _service(
            workforce=_workforce_producer(
                members=[_member(1, capabilities=[])]
            ),
            fleet=_fleet_producer(
                assets=[_asset(capabilities=[])]
            ),
        )
    )

    assert result.status is PlanningReadinessStatus.WARNING
    assert result.is_ready is True
    assert result.score.value == 90
    assert {"WORKFORCE_CAPABILITIES", "FLEET_CAPABILITIES"} <= _codes(
        result.warnings
    )


@pytest.mark.parametrize(
    ("workforce", "fleet", "expected"),
    (
        (lambda **_: None, _fleet_producer(), "WORKFORCE_PRESENT"),
        (_workforce_producer(), lambda **_: None, "FLEET_PRESENT"),
    ),
)
def test_missing_workforce_or_fleet_is_blocked(workforce, fleet, expected):
    result = _evaluate(_service(workforce=workforce, fleet=fleet))

    assert result.status is PlanningReadinessStatus.BLOCKED
    assert result.is_ready is False
    assert expected in _codes(result.blockers)
    assert result.missing_inputs


def test_zero_available_workforce_is_blocked_even_with_a_high_score():
    result = _evaluate(
        _service(
            workforce=_workforce_producer(
                statuses=[_status(1, 1, available=False)]
            )
        )
    )

    assert result.status is PlanningReadinessStatus.BLOCKED
    assert result.score.value >= 80
    assert "WORKFORCE_AVAILABLE" in _codes(result.blockers)


def test_zero_available_assets_is_blocked():
    result = _evaluate(
        _service(
            fleet=_fleet_producer(
                assets=[_asset(availability="maintenance")]
            )
        )
    )

    assert result.status is PlanningReadinessStatus.BLOCKED
    assert "FLEET_AVAILABLE" in _codes(result.blockers)


def test_stale_inputs_keep_an_explicit_stale_status():
    result = _evaluate(
        _service(
            workforce=_workforce_producer(
                members=[_member(1, updated_at=OLD)],
                statuses=[_status(1, 1, updated_at=OLD)],
            ),
            fleet=_fleet_producer(assets=[_asset(updated_at=OLD)]),
        )
    )

    assert result.status is PlanningReadinessStatus.STALE
    assert result.is_ready is False
    assert {"WORKFORCE_FRESH", "FLEET_FRESH"} <= _codes(result.blockers)


def test_partial_input_keeps_an_explicit_partial_status():
    result = _evaluate(
        _service(workforce=_workforce_producer(requirements=[]))
    )

    assert result.status is PlanningReadinessStatus.PARTIAL
    assert result.is_ready is False
    assert "WORKFORCE_COMPLETE" in _codes(result.warnings)


def test_invalid_snapshot_keeps_an_explicit_invalid_status():
    result = _evaluate(
        _service(
            workforce=_workforce_producer(
                members=[_member(1, "duplicate"), _member(2, "duplicate")],
                statuses=[_status(1, 1), _status(2, 2)],
            )
        )
    )

    assert result.status is PlanningReadinessStatus.INVALID
    assert "DUPLICATE_HUMAN_RESOURCE" in _codes(result.blockers)


@pytest.mark.parametrize(
    ("fleet", "expected_rule"),
    (
        (
            _fleet_producer(
                force_unit=OperationalUnit(external_identifier="unit-b")
            ),
            "OPERATIONAL_UNIT_MATCH",
        ),
        (
            _fleet_producer(force_date=OPERATION_DATE + timedelta(days=1)),
            "PLANNING_DATE_MATCH",
        ),
        (
            _fleet_producer(
                transform=lambda item: _replace_fingerprint(item, "tampered")
            ),
            "FINGERPRINT_VERSION_COHERENT",
        ),
        (
            _fleet_producer(
                transform=lambda item: _replace_contract_version(item, "2.0")
            ),
            "FINGERPRINT_VERSION_COHERENT",
        ),
    ),
)
def test_incompatible_scope_date_fingerprint_and_version_are_explicit(
    fleet,
    expected_rule,
):
    result = _evaluate(_service(fleet=fleet))

    assert result.status is PlanningReadinessStatus.INCOMPATIBLE
    assert expected_rule in _codes(result.blockers)


def test_scoring_is_deterministic_for_the_same_envelope():
    first = _evaluate()
    second = _evaluate()

    assert first.score == second.score
    assert first.rule_results == second.rule_results


def test_every_actionable_issue_has_a_remediation_hint():
    result = _evaluate(
        _service(workforce=lambda **_: None, fleet=lambda **_: None)
    )

    assert result.blockers
    assert all(item.remediation_hint for item in result.blockers)
    assert all(item.remediation_hint for item in result.missing_inputs)


def test_result_is_immutable_and_declares_the_legacy_flow():
    result = _evaluate()

    assert result.legacy_flow_active is True
    with pytest.raises(ValidationError):
        result.status = PlanningReadinessStatus.BLOCKED


def test_application_service_uses_the_composition_provider_once():
    class CountingProvider:
        def __init__(self):
            self.calls = 0
            self.runtime = PlanningInputRuntimeService(
                workforce_producer=_workforce_producer(),
                fleet_producer=_fleet_producer(),
                workforce_freshness_ttl=TTL,
                fleet_freshness_ttl=TTL,
            )

        def compose(self, **request):
            self.calls += 1
            return self.runtime.compose(**request)

    provider = CountingProvider()
    service = PlanningReadinessService(
        composition_provider=provider,
        evaluator=PlanningReadinessEvaluator(),
    )

    _evaluate(service)

    assert provider.calls == 1


def test_readiness_endpoint_is_compact_and_does_not_expose_raw_inputs():
    response = TestClient(app).get(
        "/api/planning/readiness",
        params={
            "organization_id": "default",
            "operational_unit_id": "default",
            "operation_date": OPERATION_DATE.isoformat(),
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "BLOCKED"
    assert len(response.content) < 15_000
    assert '"human_resources"' not in response.text
    assert '"registry"' not in response.text
    assert "Traceback" not in response.text


def test_readiness_layers_do_not_depend_on_plugins_repositories_or_importers():
    forbidden = ("app.plugins", "app.repositories", "app.importers")
    violations = []
    paths = [
        *(APP_DIR / "domain" / "planning_readiness").glob("*.py"),
        *(APP_DIR / "runtime" / "planning_readiness").glob("*.py"),
    ]
    for path in paths:
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
    assert "planning_readiness" not in planning_source
