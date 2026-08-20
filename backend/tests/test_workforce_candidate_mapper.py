from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.core_language import OperationalUnit
from app.domain.workforce_auto_planning import (
    AssignedTimeStatus,
    AssignedTimeUnit,
    CandidateOperationalUnitScopeStatus,
    ConstraintEvidence,
)
from app.plugins.workforce.application.workforce_candidate_mapper import (
    map_workforce_candidate,
)
from app.plugins.workforce.domain.consecutivity import ConsecutivitySnapshot
from app.plugins.workforce.domain.driver_shift_planning import (
    DriverShiftPlanningPublishedRow,
)
from app.plugins.workforce.domain.models import (
    OperationalCycle,
    WorkforceDriverReadiness,
    WorkforceMember,
)


ORG = "qa-workforce-candidate-mapper"
DAY = "2026-08-17"
UNIT = OperationalUnit(external_identifier="unit-north", name="North hub")


def _member(
    *,
    station: str | None = "unit-north",
    organization_id: str = ORG,
) -> WorkforceMember:
    return WorkforceMember(
        workforce_member_id=42,
        external_identifier="driver-external-42",
        display_name="Jordan Driver",
        station=station,
        employment_type="full-time",
        operational_cycle=OperationalCycle.NEXT_DAY,
        contract_start="2026-01-01",
        contract_end="2026-12-31",
        weekly_hours=40,
        capabilities=["parcel-delivery", "fragile-handling"],
        is_reserve=False,
        source_reference="candidate-mapper-test",
        created_at="2026-08-01T08:00:00+00:00",
        updated_at="2026-08-16T08:00:00+00:00",
        organization_id=organization_id,
    )


def _readiness(
    *,
    availability_status: str = "available",
    callability_status: str = "callable",
    callable_value: bool = True,
    reason: str = "Nessuna limitazione.",
    limitations: list[str] | None = None,
    workforce_member_id: int = 42,
) -> WorkforceDriverReadiness:
    return WorkforceDriverReadiness(
        workforce_member_id=workforce_member_id,
        external_identifier="driver-external-42",
        first_name="Jordan",
        last_name="Driver",
        display_name="Jordan Driver",
        station="unit-north",
        contract="full-time",
        availability_status=availability_status,
        availability_label=availability_status,
        callability_status=callability_status,
        callability_label=callability_status,
        callability_reason=reason,
        callability_tone="success" if callable_value else "danger",
        callable=callable_value,
        limitations=limitations or [],
        last_updated_at="2026-08-16T08:00:00+00:00",
    )


def _consecutivity(
    effective_consecutive_days: int | None = 3,
) -> ConsecutivitySnapshot:
    return ConsecutivitySnapshot(
        driver_id=42,
        operation_date=DAY,
        organization_id=ORG,
        effective_consecutive_days=effective_consecutive_days,
        planned_consecutive_days=6,
        threshold_warning=5,
        threshold_rest_required=6,
        status="eligible",
        calculated_status="regolare",
        reason="Consecutivita regolare.",
        calculated_at="2026-08-16T08:00:00+00:00",
        analyzed_from="2026-08-10",
        analyzed_to="2026-08-16",
    )


def _assignment(
    row_id: int,
    *,
    operation_date: str = DAY,
    shift_code: str | None = "morning",
    start_time: str | None = "08:00",
    end_time: str | None = "12:00",
    station: str | None = "unit-north",
    organization_id: str = ORG,
    workforce_member_id: int = 42,
) -> DriverShiftPlanningPublishedRow:
    return DriverShiftPlanningPublishedRow(
        id=row_id,
        organization_id=organization_id,
        driver_shift_planning_id=7,
        planning_version=2,
        workforce_member_id=workforce_member_id,
        operational_date=operation_date,
        status_code="scheduled",
        availability=True,
        shift_code=shift_code,
        start_time=start_time,
        end_time=end_time,
        station=station,
        transporter_id="not-for-core",
        provenance_summary=[{"source": "immutable-row"}],
        published_at="2026-08-16T09:00:00+00:00",
    )


def _map(
    *,
    member: WorkforceMember | None = None,
    readiness_by_date=None,
    baseline_consecutivity: ConsecutivitySnapshot | None = None,
    assignments=(),
):
    return map_workforce_candidate(
        member=member or _member(),
        requested_unit=UNIT,
        readiness_by_date=(
            readiness_by_date
            if readiness_by_date is not None
            else {DAY: _readiness()}
        ),
        baseline_consecutivity=baseline_consecutivity,
        published_assignments=assignments,
        evidence=(ConstraintEvidence(key="source", value="workforce"),),
    )


def test_complete_member_maps_to_neutral_candidate_identity_and_contract():
    candidate = _map(baseline_consecutivity=_consecutivity())

    assert candidate.workforce_member_id == "driver-external-42"
    assert candidate.human_resource.external_identifier == "driver-external-42"
    assert candidate.human_resource.display_name == "Jordan Driver"
    assert candidate.capabilities == ("parcel-delivery", "fragile-handling")
    assert candidate.applicable_contract_state.employment_type == "full-time"
    assert candidate.applicable_contract_state.contract_start == date(2026, 1, 1)
    assert candidate.applicable_contract_state.contract_end == date(2026, 12, 31)
    assert candidate.applicable_contract_state.weekly_hours == Decimal("40.0")
    assert candidate.applicable_contract_state.is_reserve is False
    assert "operational_cycle" not in candidate.model_dump(mode="json")
    assert candidate.recent_consecutivity == 3


@pytest.mark.parametrize(
    ("station", "expected"),
    [
        ("unit-north", CandidateOperationalUnitScopeStatus.MATCHED),
        ("UNIT-NORTH", CandidateOperationalUnitScopeStatus.MISMATCHED),
        (" unit-north ", CandidateOperationalUnitScopeStatus.MISMATCHED),
        ("unit-south", CandidateOperationalUnitScopeStatus.MISMATCHED),
        (None, CandidateOperationalUnitScopeStatus.UNKNOWN),
        ("   ", CandidateOperationalUnitScopeStatus.UNKNOWN),
    ],
)
def test_operational_unit_scope_uses_exact_match_only(station, expected):
    scope = _map(member=_member(station=station)).operational_unit_scope

    assert scope.status == expected
    if expected == CandidateOperationalUnitScopeStatus.UNKNOWN:
        assert scope.candidate_unit is None
    else:
        assert scope.candidate_unit.external_identifier == station


def test_consecutivity_preserves_known_and_unknown_effective_value_only():
    known = _map(baseline_consecutivity=_consecutivity(4))
    unknown_value = _map(baseline_consecutivity=_consecutivity(None))
    absent = _map(baseline_consecutivity=None)

    assert known.recent_consecutivity == 4
    assert unknown_value.recent_consecutivity is None
    assert absent.recent_consecutivity is None


def test_no_assignment_produces_known_zero_minutes():
    assigned = _map(assignments=()).already_assigned_minutes_or_hours

    assert assigned.status == AssignedTimeStatus.KNOWN
    assert assigned.value == Decimal(0)
    assert assigned.unit == AssignedTimeUnit.MINUTES


def test_all_known_durations_are_summed_as_known_minutes():
    candidate = _map(assignments=(
        _assignment(1, start_time="08:00", end_time="12:00"),
        _assignment(2, start_time="13:15", end_time="17:45"),
    ))

    assigned = candidate.already_assigned_minutes_or_hours
    assert assigned.status == AssignedTimeStatus.KNOWN
    assert assigned.value == Decimal(510)
    assert assigned.unit == AssignedTimeUnit.MINUTES
    assert all(
        item.assigned_time.status == AssignedTimeStatus.KNOWN
        for item in candidate.already_approved_assignments
    )


def test_partial_durations_preserve_only_known_minutes():
    candidate = _map(assignments=(
        _assignment(1, start_time="08:00", end_time="12:00"),
        _assignment(2, start_time=None, end_time=None),
    ))

    assigned = candidate.already_assigned_minutes_or_hours
    assert assigned.status == AssignedTimeStatus.PARTIAL
    assert assigned.value == Decimal(240)
    assert assigned.unit == AssignedTimeUnit.MINUTES


@pytest.mark.parametrize(
    ("start_time", "end_time"),
    [
        (None, None),
        ("invalid", "12:00"),
        ("12:00", "12:00"),
        ("18:00", "08:00"),
        ("08:00+02:00", "12:00+02:00"),
    ],
)
def test_undeterminable_duration_produces_unknown_assigned_time(
    start_time,
    end_time,
):
    candidate = _map(assignments=(
        _assignment(1, start_time=start_time, end_time=end_time),
    ))

    assigned = candidate.already_assigned_minutes_or_hours
    assert assigned.status == AssignedTimeStatus.UNKNOWN
    assert assigned.value is None
    assert assigned.unit is None


def test_assignment_preserves_unknown_station_and_shift_without_fallback():
    candidate = _map(assignments=(
        _assignment(1, station=None, shift_code=None),
    ))
    assignment = candidate.already_approved_assignments[0]

    assert assignment.operational_unit is None
    assert assignment.shift_identifier is None
    assert assignment.time_window.starts_at == "08:00"
    assert assignment.time_window.ends_at == "12:00"
    assert "unit-north" not in assignment.assignment_reference
    assert "not-for-core" not in str(candidate.model_dump(mode="json"))


def test_unknown_readiness_remains_unknown_and_non_callable():
    candidate = _map(readiness_by_date={
        DAY: _readiness(
            availability_status="unknown",
            callability_status="not_callable",
            callable_value=False,
            reason="Disponibilita non dichiarata.",
        )
    })
    availability = candidate.availability[0].availability

    assert availability.observed_state == "unknown"
    assert availability.available is False
    assert availability.reason == "Disponibilita non dichiarata."


@pytest.mark.parametrize(
    ("status", "callability_status", "callable_value"),
    [
        ("available", "callable", True),
        ("scheduled", "callable", True),
        ("available_limited", "limited", True),
        ("rest", "not_callable", False),
        ("holiday", "not_callable", False),
        ("sickness", "not_callable", False),
        ("leave", "not_callable", False),
        ("unavailable", "not_callable", False),
        ("unknown", "not_callable", False),
    ],
)
def test_readiness_states_are_preserved_without_reinterpretation(
    status,
    callability_status,
    callable_value,
):
    candidate = _map(readiness_by_date={
        DAY: _readiness(
            availability_status=status,
            callability_status=callability_status,
            callable_value=callable_value,
        )
    })
    availability = candidate.availability[0].availability

    assert availability.observed_state == status
    assert availability.available is callable_value


def test_limited_readiness_preserves_reason_callability_and_limitations():
    candidate = _map(readiness_by_date={
        DAY: _readiness(
            availability_status="available_limited",
            callability_status="limited",
            callable_value=True,
            reason="Guida solo van standard.",
            limitations=["Guida solo van standard.", "Turno diurno."],
        )
    })
    availability = candidate.availability[0].availability
    evidence = {(item.key, item.value) for item in candidate.evidence}

    assert availability.observed_state == "available_limited"
    assert availability.available is True
    assert availability.reason == "Guida solo van standard."
    assert (
        f"workforce-readiness:{DAY}:callability-status",
        "limited",
    ) in evidence
    assert (
        f"workforce-readiness:{DAY}:limitation:1",
        "Guida solo van standard.",
    ) in evidence
    assert (
        f"workforce-readiness:{DAY}:limitation:2",
        "Turno diurno.",
    ) in evidence


def test_mapper_rejects_cross_member_or_cross_organization_inputs():
    with pytest.raises(ValueError, match="readiness must belong"):
        _map(readiness_by_date={DAY: _readiness(workforce_member_id=99)})
    with pytest.raises(ValueError, match="member organization"):
        _map(baseline_consecutivity=_consecutivity().model_copy(
            update={"organization_id": "other-org"}
        ))
    with pytest.raises(ValueError, match="member organization"):
        _map(assignments=(_assignment(1, organization_id="other-org"),))
    with pytest.raises(ValueError, match="workforce member"):
        _map(assignments=(_assignment(1, workforce_member_id=99),))


def test_mapper_source_is_pure_and_contains_no_vertical_or_repository_coupling():
    source = (
        Path(__file__).parents[1]
        / "app"
        / "plugins"
        / "workforce"
        / "application"
        / "workforce_candidate_mapper.py"
    ).read_text(encoding="utf-8").lower()

    forbidden_terms = (
        "amazon",
        "dsp",
        "transporter_id",
        "operational_cycle",
        "repository",
        "db_session",
        "sqlalchemy",
        "fastapi",
    )
    assert all(term not in source for term in forbidden_terms)
