import ast
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.core_language import (
    AssetReference,
    HumanResource,
    OperationalUnit,
    ResourceAvailability,
    ResourceKind,
    TimeWindow,
)
from app.domain.planning_inputs import (
    PLANNING_INPUT_CONTRACT_VERSION,
    FleetPlanningInput,
    PlanningAssetRegistry,
    PlanningCoverage,
    PlanningInputContract,
    PlanningInputDependency,
    PlanningInputEnvelope,
    PlanningInputFreshness,
    PlanningInputMetadata,
    PlanningInputProvenance,
    PlanningInputScope,
    PlanningInputSource,
    PlanningInputStatus,
    PlanningInputType,
    PlanningInputVersion,
    PlanningResourceCapability,
    WorkforcePlanningInput,
    create_planning_input_snapshot,
)


NOW = datetime(2026, 7, 22, 7, 0, tzinfo=timezone.utc)
APP_DIR = Path(__file__).parents[1] / "app"


def input_scope(unit_id: str = "unit-a") -> PlanningInputScope:
    return PlanningInputScope(
        organization_id="organization-one",
        operational_unit=OperationalUnit(
            external_identifier=unit_id,
            name="Unit A" if unit_id == "unit-a" else "Unit B",
        ),
        operation_date=date(2026, 7, 22),
    )


def input_metadata(
    input_type: PlanningInputType,
    *,
    unit_id: str = "unit-a",
    produced_at: datetime = NOW - timedelta(minutes=5),
    expires_at: datetime = NOW + timedelta(minutes=25),
) -> PlanningInputMetadata:
    producer = f"{input_type.value}-plugin"
    return PlanningInputMetadata(
        input_type=input_type,
        source=PlanningInputSource(
            producer=producer,
            contract_name=f"{input_type.value}-planning-input",
            contract_version="1.0",
            source_reference=f"{producer}:snapshot-42",
            provenance=PlanningInputProvenance.PUBLIC_CONTRACT,
            produced_at=produced_at,
        ),
        scope=input_scope(unit_id),
        version=PlanningInputVersion(value="42", sequence=42),
        freshness=PlanningInputFreshness(
            observed_at=produced_at - timedelta(minutes=1),
            expires_at=expires_at,
        ),
    )


def workforce_payload(
    *,
    include_coverage: bool = True,
    availability_identifier: str = "human-001",
) -> WorkforcePlanningInput:
    return WorkforcePlanningInput(
        human_resources=(
            HumanResource(
                external_identifier="human-001",
                display_name="Resource One",
                capabilities=("license-b",),
            ),
        ),
        availability=(
            ResourceAvailability(
                resource_identifier=availability_identifier,
                resource_kind=ResourceKind.HUMAN_RESOURCE,
                available=True,
                observed_state="scheduled",
            ),
        ),
        capabilities=(
            PlanningResourceCapability(
                resource_identifier="human-001",
                resource_kind=ResourceKind.HUMAN_RESOURCE,
                capability="license-b",
            ),
        ),
        coverage=(
            PlanningCoverage(
                required=1,
                available=1,
                scheduled=1,
                unavailable=0,
                margin=0,
                status="covered",
            )
            if include_coverage
            else None
        ),
        time_windows=(
            TimeWindow(
                external_identifier="shift-morning",
                starts_at="07:00",
                ends_at="15:00",
            ),
        ),
    )


def workforce_contract(
    *,
    metadata: PlanningInputMetadata | None = None,
    payload: WorkforcePlanningInput | None = None,
    dependencies: tuple[PlanningInputDependency, ...] = (),
) -> PlanningInputContract:
    return PlanningInputContract(
        metadata=metadata
        or input_metadata(PlanningInputType.WORKFORCE),
        payload=payload or workforce_payload(),
        dependencies=dependencies,
    )


def fleet_contract(
    *,
    unit_id: str = "unit-a",
    assets: tuple[AssetReference, ...] | None = None,
) -> PlanningInputContract:
    fleet_assets = (
        (AssetReference(external_identifier="asset-001", category="van"),)
        if assets is None
        else assets
    )
    return PlanningInputContract(
        metadata=input_metadata(PlanningInputType.FLEET, unit_id=unit_id),
        payload=FleetPlanningInput(
            registry=PlanningAssetRegistry(assets=fleet_assets),
            availability=(
                (
                    ResourceAvailability(
                        resource_identifier="asset-001",
                        resource_kind=ResourceKind.ASSET,
                        available=True,
                        observed_state="available",
                    ),
                )
                if fleet_assets
                else ()
            ),
            capabilities=(
                (
                    PlanningResourceCapability(
                        resource_identifier="asset-001",
                        resource_kind=ResourceKind.ASSET,
                        capability="electric",
                    ),
                )
                if fleet_assets
                else ()
            ),
        ),
    )


def test_workforce_contract_is_ready_and_preserves_source_metadata():
    snapshot = create_planning_input_snapshot(workforce_contract(), NOW)

    assert snapshot.validation.status is PlanningInputStatus.READY
    assert snapshot.validation.issues == ()
    assert snapshot.contract.metadata.scope.identity == (
        "organization-one",
        "unit-a",
        date(2026, 7, 22),
    )
    assert snapshot.contract.metadata.source.producer == "workforce-plugin"
    assert snapshot.contract.metadata.version.sequence == 42


def test_fleet_contract_exposes_asset_registry_and_capabilities():
    snapshot = create_planning_input_snapshot(fleet_contract(), NOW)
    payload = snapshot.contract.payload

    assert snapshot.validation.status is PlanningInputStatus.READY
    assert isinstance(payload, FleetPlanningInput)
    assert payload.registry.assets[0].external_identifier == "asset-001"
    assert payload.capabilities[0].capability == "electric"


def test_expired_freshness_classifies_input_as_stale():
    produced_at = NOW - timedelta(hours=2)
    contract = workforce_contract(
        metadata=input_metadata(
            PlanningInputType.WORKFORCE,
            produced_at=produced_at,
            expires_at=NOW - timedelta(minutes=1),
        )
    )

    validation = create_planning_input_snapshot(contract, NOW).validation

    assert validation.status is PlanningInputStatus.STALE
    assert {item.code for item in validation.issues} == {"STALE_INPUT"}


def test_incomplete_workforce_contract_is_partial():
    contract = workforce_contract(
        payload=workforce_payload(include_coverage=False)
    )

    validation = create_planning_input_snapshot(contract, NOW).validation

    assert validation.status is PlanningInputStatus.PARTIAL
    assert {item.code for item in validation.issues} == {
        "MISSING_WORKFORCE_COVERAGE"
    }


def test_empty_fleet_registry_classifies_input_as_missing():
    validation = create_planning_input_snapshot(
        fleet_contract(assets=()),
        NOW,
    ).validation

    assert validation.status is PlanningInputStatus.MISSING
    assert validation.issues[0].code == "MISSING_ASSET_REGISTRY"


def test_unknown_resource_reference_classifies_input_as_invalid():
    contract = workforce_contract(
        payload=workforce_payload(availability_identifier="human-unknown")
    )

    validation = create_planning_input_snapshot(contract, NOW).validation

    assert validation.status is PlanningInputStatus.INVALID
    assert "UNKNOWN_HUMAN_RESOURCE" in {
        item.code for item in validation.issues
    }


@pytest.mark.parametrize(
    ("required", "expected"),
    (
        (True, PlanningInputStatus.MISSING),
        (False, PlanningInputStatus.PARTIAL),
    ),
)
def test_dependencies_affect_input_status_without_domain_decisions(
    required,
    expected,
):
    contract = workforce_contract(
        dependencies=(
            PlanningInputDependency(
                dependency_id="configuration:organization-one:unit-a",
                producer="configuration-engine",
                required=required,
                satisfied=False,
            ),
        )
    )

    validation = create_planning_input_snapshot(contract, NOW).validation

    assert validation.status is expected


def test_contract_rejects_mismatched_metadata_and_payload_types():
    with pytest.raises(ValidationError, match="input types must match"):
        PlanningInputContract(
            metadata=input_metadata(PlanningInputType.WORKFORCE),
            payload=fleet_contract().payload,
        )


def test_envelope_requires_one_scope_and_one_snapshot_per_input_type():
    workforce = create_planning_input_snapshot(workforce_contract(), NOW)
    fleet = create_planning_input_snapshot(fleet_contract(), NOW)
    envelope = PlanningInputEnvelope(
        envelope_id="planning-input:unit-a:2026-07-22",
        scope=input_scope(),
        version=PlanningInputVersion(value="1", sequence=1),
        created_at=NOW,
        snapshots=(workforce, fleet),
    )

    assert envelope.contract_version == PLANNING_INPUT_CONTRACT_VERSION
    assert [
        item.contract.metadata.input_type for item in envelope.snapshots
    ] == [PlanningInputType.WORKFORCE, PlanningInputType.FLEET]

    with pytest.raises(ValidationError, match="cannot repeat an input type"):
        PlanningInputEnvelope(
            envelope_id="duplicate",
            scope=input_scope(),
            version=PlanningInputVersion(value="2"),
            created_at=NOW,
            snapshots=(workforce, workforce),
        )


def test_envelope_rejects_a_snapshot_from_another_operational_unit():
    workforce = create_planning_input_snapshot(workforce_contract(), NOW)
    fleet = create_planning_input_snapshot(
        fleet_contract(unit_id="unit-b"),
        NOW,
    )

    with pytest.raises(ValidationError, match="share the envelope scope"):
        PlanningInputEnvelope(
            envelope_id="mixed-scope",
            scope=input_scope(),
            version=PlanningInputVersion(value="1"),
            created_at=NOW,
            snapshots=(workforce, fleet),
        )


def test_planning_input_models_are_immutable():
    scope = input_scope()

    with pytest.raises(ValidationError, match="frozen"):
        scope.organization_id = "another-organization"


def test_planning_input_layer_has_no_outer_layer_dependencies():
    package = APP_DIR / "domain" / "planning_inputs"
    forbidden = (
        "app.adapters",
        "app.api",
        "app.plugins",
        "app.repositories",
        "app.schemas",
        "app.services",
    )
    violations: list[str] = []

    for path in package.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            module = None
            if isinstance(node, ast.ImportFrom):
                module = node.module
            elif isinstance(node, ast.Import) and node.names:
                module = node.names[0].name
            if module and module.startswith(forbidden):
                violations.append(f"{path.name}: {module}")

    assert violations == []


def test_current_planning_engine_does_not_consume_the_new_layer():
    source = (
        APP_DIR / "services" / "planning_generation_service.py"
    ).read_text(encoding="utf-8")

    assert "app.domain.planning_inputs" not in source
    assert "PlanningInputEnvelope" not in source
