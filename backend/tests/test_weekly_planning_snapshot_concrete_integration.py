from datetime import date, datetime, timezone
from decimal import Decimal
import re

import pytest
from pydantic import ValidationError

from app.adapters.amazon.coverage_operational_demand_input_mapper import (
    AMAZON_COVERAGE_DEMAND_SOURCE_CONTEXT,
)
from app.adapters.amazon.operational_demand_provider import (
    AmazonOperationalDemandProviderAdapter,
)
from app.core.configuration.models import (
    ConfigurationScope,
    ConfigurationSection,
    ConfigurationValue,
    ConfigurationValueSource,
)
from app.core.configuration.planning_operational_unit_binding_provider import (
    PLANNING_BINDING_ADAPTER_ID,
    PLANNING_BINDING_SECTION_KEY,
    PLANNING_BINDING_VALUE_KEY,
)
from app.core.configuration.repository import save_revision
from app.core.database import db_session
from app.domain.core_language import OperationalUnit
from app.domain.workforce_auto_planning import (
    AssignedTimeStatus,
    AssignedTimeUnit,
    WeeklyPlanningInputSnapshot,
    WeeklyPlanningInputSnapshotComposer,
    compute_weekly_planning_input_fingerprint,
)
from app.plugins.workforce.application import consecutivity_service
from app.plugins.workforce.application.auto_planning_candidate_provider import (
    WorkforceCandidateSnapshotProviderAdapter,
)
from app.plugins.workforce.domain.coverage import (
    CoverageSource,
    ForecastAuthorityStatus,
    ImportedDailyCoverageRequirement,
    required_capacity_for,
)
from app.plugins.workforce.infrastructure.coverage_repository import (
    persist_imported_requirements,
)


ORG_A = "snapshot-integration-org-a"
ORG_B = "snapshot-integration-org-b"
UNIT = OperationalUnit(external_identifier="DLO2", name="DLO2")
OTHER_UNIT = OperationalUnit(external_identifier="DLO3", name="DLO3")
PERIOD_START = date(2026, 8, 24)
PERIOD_END = date(2026, 8, 30)
NOW = "2026-08-21T08:00:00+00:00"
CREATED_AT = datetime(2026, 8, 21, 8, 0, tzinfo=timezone.utc)
POLICY_ID = "amazon-weekly-workforce-policy"
POLICY_VERSION = "1"


def _save_binding(organization_id: str, unit: OperationalUnit = UNIT) -> None:
    save_revision(
        scope=ConfigurationScope(
            organization_id=organization_id,
            adapter_id=PLANNING_BINDING_ADAPTER_ID,
        ),
        sections=[
            ConfigurationSection(
                key=PLANNING_BINDING_SECTION_KEY,
                values=[
                    ConfigurationValue(
                        key=PLANNING_BINDING_VALUE_KEY,
                        value=[
                            {
                                "demand_source_context": (
                                    AMAZON_COVERAGE_DEMAND_SOURCE_CONTEXT
                                ),
                                "operational_unit": unit.model_dump(mode="json"),
                                "active": True,
                            }
                        ],
                        source=ConfigurationValueSource.FUTURE_ADAPTER,
                    )
                ],
            )
        ],
        created_by="snapshot-integration-test",
    )


def _coverage_requirement(
    *,
    operation_date: date,
    cycle: str,
    segment: str | None,
    forecast_routes: int,
    source_identity: str,
) -> ImportedDailyCoverageRequirement:
    return ImportedDailyCoverageRequirement(
        operational_date=operation_date.isoformat(),
        station=None,
        operational_cycle=cycle,
        coverage_segment=segment,
        forecast_routes=forecast_routes,
        reserve_percentage=10,
        required_capacity=required_capacity_for(forecast_routes),
        source=CoverageSource.IMPORT.value,
        source_reference="snapshot-integration.xlsx",
        source_identity=source_identity,
        authority_status=ForecastAuthorityStatus.AUTHORITATIVE.value,
    )


def _persist_coverage() -> None:
    requirements_a = (
        _coverage_requirement(
            operation_date=date(2026, 8, 24),
            cycle="NEXT_DAY",
            segment=None,
            forecast_routes=76,
            source_identity="snapshot-a-next-day",
        ),
        _coverage_requirement(
            operation_date=date(2026, 8, 25),
            cycle="SAME_DAY",
            segment="A",
            forecast_routes=20,
            source_identity="snapshot-a-same-day-a",
        ),
        _coverage_requirement(
            operation_date=date(2026, 8, 26),
            cycle="SAME_DAY",
            segment="B_C",
            forecast_routes=18,
            source_identity="snapshot-a-same-day-b-c",
        ),
    )
    requirements_b = (
        _coverage_requirement(
            operation_date=date(2026, 8, 24),
            cycle="NEXT_DAY",
            segment=None,
            forecast_routes=999,
            source_identity="snapshot-b-next-day",
        ),
    )
    with db_session() as conn:
        persist_imported_requirements(
            conn,
            requirements_a,
            organization_id=ORG_A,
            now=NOW,
        )
        persist_imported_requirements(
            conn,
            requirements_b,
            organization_id=ORG_B,
            now=NOW,
        )


def _member(
    *,
    organization_id: str,
    external_identifier: str,
    display_name: str,
) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_members (
                external_identifier, display_name, role, employment_type,
                weekly_hours, capabilities, active, source_reference,
                created_at, updated_at, first_name, last_name, station,
                operational_notes, is_reserve, organization_id
            ) VALUES (?, ?, 'driver', 'full-time', 40, ?, 1, ?, ?, ?, ?, ?, ?,
                      NULL, 0, ?)
            """,
            (
                external_identifier,
                display_name,
                '["amazon-workload-next-day"]',
                "snapshot-integration-test",
                NOW,
                NOW,
                display_name.split()[0],
                display_name.split()[-1],
                UNIT.external_identifier,
                organization_id,
            ),
        )
        return int(cursor.lastrowid)


def _day_status(
    *,
    organization_id: str,
    member_id: int,
    operation_date: date,
    status_code: str,
) -> None:
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO workforce_day_statuses (
                workforce_member_id, date, status_code, availability,
                source_reference, observed_or_confirmed, updated_at,
                organization_id
            ) VALUES (?, ?, ?, ?, 'snapshot-integration-test', 'manual', ?, ?)
            """,
            (
                member_id,
                operation_date.isoformat(),
                status_code,
                int(status_code in {"available", "scheduled"}),
                NOW,
                organization_id,
            ),
        )


def _active_planning(organization_id: str) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO driver_shift_plannings (
                organization_id, label, period_start, period_end, status,
                version, created_at, created_by, updated_at
            ) VALUES (?, 'Snapshot integration', ?, ?, 'ACTIVE', 1, ?, ?, ?)
            """,
            (
                organization_id,
                PERIOD_START.isoformat(),
                PERIOD_END.isoformat(),
                NOW,
                "snapshot-integration-test",
                NOW,
            ),
        )
        return int(cursor.lastrowid)


def _published_assignment(
    *,
    organization_id: str,
    planning_id: int,
    member_id: int,
    operation_date: date,
) -> None:
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO driver_shift_planning_published_rows (
                organization_id, driver_shift_planning_id, planning_version,
                workforce_member_id, operational_date, status_code,
                availability, shift_code, start_time, end_time, station,
                provenance_summary, published_at
            ) VALUES (?, ?, 1, ?, ?, 'scheduled', 1, 'C1', '08:00', '12:00',
                      ?, '[]', ?)
            """,
            (
                organization_id,
                planning_id,
                member_id,
                operation_date.isoformat(),
                UNIT.external_identifier,
                NOW,
            ),
        )


def _arrange_concrete_sources(monkeypatch) -> None:
    monkeypatch.setattr(
        consecutivity_service,
        "_organization_today",
        lambda _organization_id: date(2026, 8, 21),
    )
    _save_binding(ORG_A)
    _persist_coverage()

    first_member = _member(
        organization_id=ORG_A,
        external_identifier="driver-one",
        display_name="Driver One",
    )
    second_member = _member(
        organization_id=ORG_A,
        external_identifier="driver-two",
        display_name="Driver Two",
    )
    foreign_member = _member(
        organization_id=ORG_B,
        external_identifier="driver-foreign",
        display_name="Driver Foreign",
    )

    _day_status(
        organization_id=ORG_A,
        member_id=first_member,
        operation_date=date(2026, 8, 18),
        status_code="rest",
    )
    for operation_date in (date(2026, 8, 19), date(2026, 8, 20)):
        _day_status(
            organization_id=ORG_A,
            member_id=first_member,
            operation_date=operation_date,
            status_code="scheduled",
        )
    _day_status(
        organization_id=ORG_A,
        member_id=first_member,
        operation_date=PERIOD_START,
        status_code="available",
    )
    _day_status(
        organization_id=ORG_A,
        member_id=second_member,
        operation_date=date(2026, 8, 20),
        status_code="rest",
    )
    _day_status(
        organization_id=ORG_A,
        member_id=second_member,
        operation_date=PERIOD_START,
        status_code="rest",
    )
    _day_status(
        organization_id=ORG_B,
        member_id=foreign_member,
        operation_date=PERIOD_START,
        status_code="available",
    )

    planning = _active_planning(ORG_A)
    _published_assignment(
        organization_id=ORG_A,
        planning_id=planning,
        member_id=first_member,
        operation_date=PERIOD_START,
    )
    foreign_planning = _active_planning(ORG_B)
    _published_assignment(
        organization_id=ORG_B,
        planning_id=foreign_planning,
        member_id=foreign_member,
        operation_date=PERIOD_START,
    )


def _concrete_composer():
    demand_provider = AmazonOperationalDemandProviderAdapter()
    candidate_provider = WorkforceCandidateSnapshotProviderAdapter()
    return (
        WeeklyPlanningInputSnapshotComposer(
            demand_provider=demand_provider,
            candidate_provider=candidate_provider,
        ),
        demand_provider,
        candidate_provider,
    )


def _compose(
    composer: WeeklyPlanningInputSnapshotComposer,
    *,
    snapshot_id: str = "snapshot-concrete-1",
    created_at: datetime = CREATED_AT,
) -> WeeklyPlanningInputSnapshot:
    return composer.compose(
        snapshot_id=snapshot_id,
        organization_id=ORG_A,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        operational_unit=UNIT,
        policy_set_identifier=POLICY_ID,
        policy_set_version=POLICY_VERSION,
        created_at=created_at,
    )


def _availability(candidate, operation_date: date):
    return next(item for item in candidate.availability if item.date == operation_date)


def _fingerprint(snapshot, *, demands=None, candidates=None) -> str:
    return compute_weekly_planning_input_fingerprint(
        organization_id=snapshot.organization_id,
        period_start=snapshot.period_start,
        period_end=snapshot.period_end,
        operational_unit=snapshot.operational_unit,
        demands=demands if demands is not None else snapshot.demands,
        workforce_candidates=(
            candidates
            if candidates is not None
            else snapshot.workforce_candidates
        ),
        policy_set_identifier=snapshot.policy_set_identifier,
        policy_set_version=snapshot.policy_set_version,
    )


def test_concrete_providers_compose_one_scoped_weekly_snapshot(monkeypatch):
    _arrange_concrete_sources(monkeypatch)
    composer, demand_provider, candidate_provider = _concrete_composer()
    calls = {"demands": 0, "candidates": 0}
    real_demands = demand_provider.get_demands
    real_candidates = candidate_provider.get_candidates

    def counted_demands(**kwargs):
        calls["demands"] += 1
        return real_demands(**kwargs)

    def counted_candidates(**kwargs):
        calls["candidates"] += 1
        return real_candidates(**kwargs)

    monkeypatch.setattr(demand_provider, "get_demands", counted_demands)
    monkeypatch.setattr(candidate_provider, "get_candidates", counted_candidates)

    snapshot = _compose(composer)

    assert calls == {"demands": 1, "candidates": 1}
    assert snapshot.organization_id == ORG_A
    assert snapshot.operational_unit == UNIT
    assert (snapshot.period_start, snapshot.period_end) == (
        PERIOD_START,
        PERIOD_END,
    )
    assert snapshot.policy_set_identifier == POLICY_ID
    assert snapshot.policy_set_version == POLICY_VERSION
    assert re.fullmatch(r"[0-9a-f]{64}", snapshot.fingerprint)

    assert len(snapshot.demands) == 3
    assert {demand.capability_or_workload for demand in snapshot.demands} == {
        "amazon-workload-next-day",
        "amazon-workload-same-day-a",
        "amazon-workload-same-day-b-c",
    }
    assert all(demand.organization_id == ORG_A for demand in snapshot.demands)
    assert all(demand.operational_unit == UNIT for demand in snapshot.demands)
    next_day = next(
        demand
        for demand in snapshot.demands
        if demand.capability_or_workload == "amazon-workload-next-day"
    )
    assert next_day.base_quantity == 76
    assert next_day.target_quantity == 84
    assert next_day.applied_policy.identifier == "amazon-operational-buffer"

    candidates = {
        candidate.workforce_member_id: candidate
        for candidate in snapshot.workforce_candidates
    }
    assert set(candidates) == {"driver-one", "driver-two"}
    assert "driver-foreign" not in candidates

    first = candidates["driver-one"]
    second = candidates["driver-two"]
    assert _availability(first, PERIOD_START).availability.observed_state == "available"
    assert _availability(first, PERIOD_START).availability.available is True
    assert _availability(second, PERIOD_START).availability.observed_state == "rest"
    assert _availability(second, PERIOD_START).availability.available is False
    assert first.recent_consecutivity == 2
    assert second.recent_consecutivity == 0

    assert len(first.already_approved_assignments) == 1
    assignment = first.already_approved_assignments[0]
    assert assignment.shift_identifier == "C1"
    assert assignment.operational_unit is not None
    assert (
        assignment.operational_unit.external_identifier
        == UNIT.external_identifier
    )
    assert assignment.assigned_time.status == AssignedTimeStatus.KNOWN
    assert assignment.assigned_time.value == Decimal("240")
    assert assignment.assigned_time.unit == AssignedTimeUnit.MINUTES
    assert second.already_approved_assignments == ()
    assert (
        second.already_assigned_minutes_or_hours.status
        == AssignedTimeStatus.KNOWN
    )
    assert second.already_assigned_minutes_or_hours.value == Decimal("0")
    assert second.already_assigned_minutes_or_hours.unit == AssignedTimeUnit.MINUTES

    assert _fingerprint(
        snapshot,
        demands=tuple(reversed(snapshot.demands)),
        candidates=tuple(reversed(snapshot.workforce_candidates)),
    ) == snapshot.fingerprint
    assert calls == {"demands": 1, "candidates": 1}


def test_concrete_snapshot_fingerprint_tracks_logical_inputs_only(monkeypatch):
    _arrange_concrete_sources(monkeypatch)
    composer, _demand_provider, _candidate_provider = _concrete_composer()

    first = _compose(composer)
    second = _compose(
        composer,
        snapshot_id="snapshot-concrete-2",
        created_at=datetime(2026, 8, 22, 9, 30, tzinfo=timezone.utc),
    )

    assert first.fingerprint == second.fingerprint
    assert _fingerprint(
        first,
        demands=tuple(reversed(first.demands)),
        candidates=tuple(reversed(first.workforce_candidates)),
    ) == first.fingerprint

    changed_demand = first.demands[0].model_copy(
        update={
            "base_quantity": first.demands[0].base_quantity + 1,
            "target_quantity": first.demands[0].target_quantity + 1,
        }
    )
    assert _fingerprint(
        first,
        demands=(changed_demand, *first.demands[1:]),
    ) != first.fingerprint

    changed_candidate = first.workforce_candidates[0].model_copy(
        update={"recent_consecutivity": 99}
    )
    assert _fingerprint(
        first,
        candidates=(changed_candidate, *first.workforce_candidates[1:]),
    ) != first.fingerprint


def test_snapshot_rejects_a_demand_from_another_operational_unit(monkeypatch):
    _arrange_concrete_sources(monkeypatch)
    composer, _demand_provider, _candidate_provider = _concrete_composer()
    snapshot = _compose(composer)
    foreign_demand = snapshot.demands[0].model_copy(
        update={"operational_unit": OTHER_UNIT}
    )

    payload = snapshot.model_dump()
    payload["demands"] = (foreign_demand, *snapshot.demands[1:])

    with pytest.raises(
        ValidationError,
        match="all demands must belong to the snapshot operational unit",
    ):
        WeeklyPlanningInputSnapshot.model_validate(payload)
