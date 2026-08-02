from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.domain.core_language import OperationalUnit
from app.domain.planning_inputs import (
    FleetPlanningInput,
    PlanningInputStatus,
    PlanningInputType,
    WorkforcePlanningInput,
    compose_planning_input_envelope,
)
from app.plugins.fleet.application import planning_input_producer as fleet_producer
from app.plugins.fleet.domain.models import Asset
from app.plugins.workforce.application import (
    planning_input_producer as workforce_producer,
)
from app.plugins.workforce.domain.models import (
    WorkforceDayStatus,
    WorkforceMember,
    WorkforceRequirement,
    WorkforceValueOrigin,
)


NOW = datetime(2026, 7, 22, 7, 0, tzinfo=UTC)
RECENT = datetime(2026, 7, 22, 6, 45, tzinfo=UTC)
OLD = datetime(2026, 7, 22, 4, 0, tzinfo=UTC)
OPERATION_DATE = date(2026, 7, 22)
TTL = timedelta(hours=1)
UNIT = OperationalUnit(external_identifier="unit-a", name="Unit A")


def iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def member(
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
        created_at=iso(updated_at),
        updated_at=iso(updated_at),
    )


def day_status(
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
        updated_at=iso(updated_at),
    )


def requirement(required: int = 1) -> WorkforceRequirement:
    return WorkforceRequirement(
        requirement_id=1,
        date=OPERATION_DATE.isoformat(),
        operational_unit_id=UNIT.external_identifier,
        required_resources=required,
        required_capabilities=["license-b"],
        source="synthetic",
        version=1,
    )


def asset(
    asset_id: int,
    *,
    availability: str = "available",
    updated_at: datetime = RECENT,
) -> Asset:
    return Asset(
        id=asset_id,
        external_identifier=f"asset-{asset_id:03d}",
        plate=f"QA{asset_id:05d}",
        category="van",
        status="active",
        availability=availability,
        capabilities=["electric"],
        created_at=iso(updated_at),
        updated_at=iso(updated_at),
    )


def workforce_snapshot(
    *,
    members=(member(1),),
    statuses=(day_status(1, 1),),
    requirements=(requirement(),),
    assessed_at: datetime = NOW,
):
    return workforce_producer.build_workforce_planning_input_snapshot(
        organization_id="organization-one",
        operational_unit=UNIT,
        operation_date=OPERATION_DATE,
        members=members,
        statuses=statuses,
        requirements=requirements,
        assessed_at=assessed_at,
        freshness_ttl=TTL,
    )


def fleet_snapshot(
    *,
    assets=(asset(1),),
    unit: OperationalUnit = UNIT,
    assessed_at: datetime = NOW,
):
    return fleet_producer.build_fleet_planning_input_snapshot(
        organization_id="organization-one",
        operational_unit=unit,
        operation_date=OPERATION_DATE,
        assets=assets,
        assessed_at=assessed_at,
        freshness_ttl=TTL,
    )


def test_workforce_producer_exports_ready_scoped_core_contract():
    snapshot = workforce_snapshot(
        members=(member(2), member(1)),
        statuses=(day_status(2, 2), day_status(1, 1)),
        requirements=(requirement(2),),
    )
    metadata = snapshot.contract.metadata
    payload = snapshot.contract.payload

    assert snapshot.validation.status is PlanningInputStatus.READY
    assert metadata.input_type is PlanningInputType.WORKFORCE
    assert metadata.scope.identity == (
        "organization-one",
        "unit-a",
        OPERATION_DATE,
    )
    assert metadata.source.producer == "workforce-plugin"
    assert metadata.source.source_reference.endswith(metadata.version.value)
    assert metadata.freshness.observed_at == RECENT
    assert isinstance(payload, WorkforcePlanningInput)
    assert [item.external_identifier for item in payload.human_resources] == [
        "human-001",
        "human-002",
    ]
    assert len(payload.availability) == 2
    assert len(payload.capabilities) == 2
    assert payload.coverage is not None
    assert payload.coverage.margin == 0
    assert len(payload.time_windows) == 1


def test_workforce_fingerprint_is_stable_for_equivalent_source_order():
    first = workforce_snapshot(
        members=(member(1), member(2)),
        statuses=(day_status(1, 1), day_status(2, 2)),
        requirements=(requirement(2),),
    )
    second = workforce_snapshot(
        members=(member(2), member(1)),
        statuses=(day_status(2, 2), day_status(1, 1)),
        requirements=(requirement(2),),
    )

    assert first.contract.metadata.version == second.contract.metadata.version
    assert first.snapshot_id == second.snapshot_id


def test_workforce_producer_reports_partial_missing_and_stale():
    partial = workforce_snapshot(requirements=())
    missing = workforce_snapshot(members=(), statuses=(), requirements=())
    stale = workforce_snapshot(
        members=(member(1, updated_at=OLD),),
        statuses=(day_status(1, 1, updated_at=OLD),),
    )

    assert partial.validation.status is PlanningInputStatus.PARTIAL
    assert missing.validation.status is PlanningInputStatus.MISSING
    assert stale.validation.status is PlanningInputStatus.STALE


def test_workforce_producer_exposes_invalid_duplicate_identity():
    snapshot = workforce_snapshot(
        members=(member(1, "duplicate"), member(2, "duplicate")),
        statuses=(day_status(1, 1), day_status(2, 2)),
        requirements=(requirement(2),),
    )

    assert snapshot.validation.status is PlanningInputStatus.INVALID
    assert "DUPLICATE_HUMAN_RESOURCE" in {
        item.code for item in snapshot.validation.issues
    }


def test_fleet_producer_exports_registry_availability_and_capability():
    snapshot = fleet_snapshot(
        assets=(asset(2, availability="maintenance"), asset(1)),
    )
    metadata = snapshot.contract.metadata
    payload = snapshot.contract.payload

    assert snapshot.validation.status is PlanningInputStatus.READY
    assert metadata.input_type is PlanningInputType.FLEET
    assert metadata.scope.operational_unit == UNIT
    assert metadata.source.producer == "fleet-plugin"
    assert metadata.source.source_reference.endswith(metadata.version.value)
    assert isinstance(payload, FleetPlanningInput)
    assert [item.external_identifier for item in payload.registry.assets] == [
        "asset-001",
        "asset-002",
    ]
    assert [item.available for item in payload.availability] == [True, False]
    assert [item.capability for item in payload.capabilities] == [
        "electric",
        "electric",
    ]


def test_fleet_fingerprint_is_stable_and_empty_registry_is_missing():
    first = fleet_snapshot(assets=(asset(1), asset(2)))
    second = fleet_snapshot(assets=(asset(2), asset(1)))
    missing = fleet_snapshot(assets=())

    assert first.contract.metadata.version == second.contract.metadata.version
    assert missing.validation.status is PlanningInputStatus.MISSING


def test_future_fleet_observation_is_invalid():
    snapshot = fleet_snapshot(
        assets=(asset(1, updated_at=NOW + timedelta(minutes=1)),),
    )

    assert snapshot.validation.status is PlanningInputStatus.INVALID
    assert "OBSERVATION_AFTER_PRODUCTION" in {
        item.code for item in snapshot.validation.issues
    }


def test_plugin_producers_read_only_their_existing_sources(monkeypatch):
    status_filters = []
    requirement_filters = []
    monkeypatch.setattr(
        workforce_producer.read_repository,
        "list_members",
        lambda organization_id=None: [member(1)],
    )
    monkeypatch.setattr(
        workforce_producer.read_repository,
        "list_statuses",
        lambda date_from=None, date_to=None, member_id=None, organization_id=None: (
            status_filters.append((date_from, date_to, organization_id)) or [day_status(1, 1)]
        ),
    )
    monkeypatch.setattr(
        workforce_producer.read_repository,
        "list_requirements",
        lambda date_from, date_to, organization_id=None: (
            requirement_filters.append((date_from, date_to, organization_id))
            or [requirement()]
        ),
    )
    monkeypatch.setattr(
        fleet_producer.repository,
        "list_assets",
        lambda: [asset(1)],
    )

    workforce = workforce_producer.produce_workforce_planning_input_snapshot(
        organization_id="organization-one",
        operational_unit=UNIT,
        operation_date=OPERATION_DATE,
        assessed_at=NOW,
        freshness_ttl=TTL,
    )
    fleet = fleet_producer.produce_fleet_planning_input_snapshot(
        organization_id="organization-one",
        operational_unit=UNIT,
        operation_date=OPERATION_DATE,
        assessed_at=NOW,
        freshness_ttl=TTL,
    )

    expected_filters = (
        OPERATION_DATE.isoformat(), OPERATION_DATE.isoformat(),
        "organization-one",
    )
    assert expected_filters in status_filters
    assert requirement_filters == [expected_filters]
    assert workforce.validation.status is PlanningInputStatus.READY
    assert fleet.validation.status is PlanningInputStatus.READY


def test_composer_creates_deterministic_envelope_from_both_plugins():
    workforce = workforce_snapshot()
    fleet = fleet_snapshot()

    first = compose_planning_input_envelope(
        workforce,
        fleet,
        created_at=NOW,
    )
    second = compose_planning_input_envelope(
        workforce,
        fleet,
        created_at=NOW + timedelta(minutes=1),
    )

    assert first.scope.identity == (
        "organization-one",
        "unit-a",
        OPERATION_DATE,
    )
    assert first.version == second.version
    assert [
        item.contract.metadata.input_type for item in first.snapshots
    ] == [PlanningInputType.WORKFORCE, PlanningInputType.FLEET]


def test_composer_rejects_wrong_type_and_mixed_scope():
    workforce = workforce_snapshot()
    fleet = fleet_snapshot()

    with pytest.raises(ValueError, match="Expected a workforce snapshot"):
        compose_planning_input_envelope(fleet, workforce, created_at=NOW)

    with pytest.raises(ValidationError, match="share the envelope scope"):
        compose_planning_input_envelope(
            workforce,
            fleet_snapshot(
                unit=OperationalUnit(external_identifier="unit-b")
            ),
            created_at=NOW,
        )
