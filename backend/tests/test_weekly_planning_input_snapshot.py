from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.core_language import (
    HumanResource,
    OperationalUnit,
    ResourceAvailability,
    ResourceKind,
    TimeWindow,
)
from app.domain.workforce_auto_planning import (
    ApprovedAssignmentSnapshot,
    AssignedTimeSnapshot,
    AssignedTimeStatus,
    AssignedTimeUnit,
    ContractStateSourceKind,
    ConstraintEvidence,
    CurrentMemberContractStateSnapshot,
    OperationalDemand,
    WeeklyPlanningInputSnapshot,
    WorkforceCandidateAvailabilitySnapshot,
    WorkforceCandidateSnapshot,
)


PERIOD_START = date(2026, 8, 17)
PERIOD_END = date(2026, 8, 23)
UNIT = OperationalUnit(external_identifier="unit-north", name="North hub")
WINDOW = TimeWindow(
    external_identifier="morning-window",
    starts_at="08:00",
    ends_at="16:00",
)


def _demand(*, organization_id: str = "org-1", day: date = PERIOD_START):
    return OperationalDemand(
        organization_id=organization_id,
        operational_unit=UNIT,
        date=day,
        time_window=WINDOW,
        capability_or_workload="parcel-delivery",
        base_quantity=8,
        target_quantity=9,
        source="weekly-forecast",
    )


def _candidate(
    *,
    organization_id: str = "org-1",
    recent_consecutivity: int | None = 2,
    contract_state: CurrentMemberContractStateSnapshot | None = None,
):
    resource = HumanResource(
        external_identifier="member-42",
        display_name="Jordan Driver",
        capabilities=("parcel-delivery",),
    )
    assigned_time = AssignedTimeSnapshot(
        value=Decimal("8"), unit=AssignedTimeUnit.HOURS
    )
    return WorkforceCandidateSnapshot(
        organization_id=organization_id,
        human_resource=resource,
        availability=(
            WorkforceCandidateAvailabilitySnapshot(
                date=PERIOD_START,
                time_window=WINDOW,
                availability=ResourceAvailability(
                    resource_identifier=resource.external_identifier,
                    resource_kind=ResourceKind.HUMAN_RESOURCE,
                    available=True,
                    observed_state="eligible",
                    origin="workforce-calendar",
                ),
            ),
        ),
        applicable_contract_state=(
            contract_state
            if contract_state is not None
            else CurrentMemberContractStateSnapshot(
                employment_type="full-time",
                contract_start=date(2026, 1, 1),
                contract_end=date(2026, 12, 31),
                weekly_hours=Decimal("40"),
                is_reserve=False,
            )
        ),
        recent_consecutivity=recent_consecutivity,
        already_approved_assignments=(
            ApprovedAssignmentSnapshot(
                assignment_reference="assignment-1",
                date=PERIOD_START,
                operational_unit=UNIT,
                shift_identifier="morning",
                time_window=WINDOW,
                assigned_time=assigned_time,
            ),
        ),
        already_assigned_minutes_or_hours=assigned_time,
        evidence=(ConstraintEvidence(key="source", value="calendar"),),
    )


def _snapshot(**overrides):
    values = {
        "snapshot_id": "snapshot-week-34",
        "organization_id": "org-1",
        "period_start": PERIOD_START,
        "period_end": PERIOD_END,
        "operational_unit": UNIT,
        "demands": (_demand(),),
        "workforce_candidates": (_candidate(),),
        "policy_set_identifier": "standard-weekly-policy",
        "policy_set_version": "1",
        "created_at": datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc),
        "fingerprint": "sha256:input-snapshot",
    }
    values.update(overrides)
    return WeeklyPlanningInputSnapshot(**values)


def test_valid_weekly_snapshot_reuses_existing_neutral_models():
    snapshot = _snapshot()

    assert isinstance(snapshot.demands[0], OperationalDemand)
    assert isinstance(snapshot.workforce_candidates[0].human_resource, HumanResource)
    assert snapshot.workforce_candidates[0].workforce_member_id == "member-42"
    assert snapshot.workforce_candidates[0].capabilities == ("parcel-delivery",)
    assert snapshot.fingerprint == "sha256:input-snapshot"


def test_snapshot_collections_and_models_are_immutable():
    snapshot = _snapshot()

    assert isinstance(snapshot.demands, tuple)
    assert isinstance(snapshot.workforce_candidates, tuple)
    assert isinstance(snapshot.workforce_candidates[0].availability, tuple)
    assert isinstance(
        snapshot.workforce_candidates[0].already_approved_assignments, tuple
    )
    assert isinstance(snapshot.workforce_candidates[0].evidence, tuple)
    with pytest.raises(ValidationError):
        snapshot.fingerprint = "changed"
    with pytest.raises(ValidationError):
        snapshot.workforce_candidates[0].recent_consecutivity = 4


def test_demand_organization_mismatch_is_rejected():
    with pytest.raises(ValidationError, match="all demands must belong"):
        _snapshot(demands=(_demand(organization_id="org-2"),))


def test_candidate_organization_mismatch_is_rejected():
    with pytest.raises(ValidationError, match="all workforce candidates"):
        _snapshot(workforce_candidates=(_candidate(organization_id="org-2"),))


def test_demand_outside_snapshot_period_is_rejected():
    with pytest.raises(ValidationError, match="within the snapshot period"):
        _snapshot(demands=(_demand(day=date(2026, 8, 24)),))


@pytest.mark.parametrize("fingerprint", ["", "   "])
def test_empty_fingerprint_is_rejected(fingerprint):
    with pytest.raises(ValidationError):
        _snapshot(fingerprint=fingerprint)


def test_invalid_period_is_rejected():
    with pytest.raises(ValidationError, match="period_end cannot precede"):
        _snapshot(period_start=PERIOD_END, period_end=PERIOD_START)


def test_candidate_availability_must_describe_the_same_human_resource():
    resource = HumanResource(external_identifier="member-42")
    with pytest.raises(ValidationError, match="must belong"):
        WorkforceCandidateSnapshot(
            organization_id="org-1",
            human_resource=resource,
            availability=(
                WorkforceCandidateAvailabilitySnapshot(
                    date=PERIOD_START,
                    availability=ResourceAvailability(
                        resource_identifier="member-other",
                        resource_kind=ResourceKind.HUMAN_RESOURCE,
                        available=True,
                    ),
                ),
            ),
            applicable_contract_state=CurrentMemberContractStateSnapshot(),
            recent_consecutivity=0,
            already_assigned_minutes_or_hours=AssignedTimeSnapshot(
                value=0, unit=AssignedTimeUnit.MINUTES
            ),
        )


def test_recent_consecutivity_distinguishes_known_zero_from_unknown():
    known_zero = _candidate(recent_consecutivity=0)
    unknown = _candidate(recent_consecutivity=None)

    assert known_zero.recent_consecutivity == 0
    assert unknown.recent_consecutivity is None


def test_positive_recent_consecutivity_remains_valid():
    assert _candidate().recent_consecutivity == 2


def test_negative_recent_consecutivity_is_rejected():
    values = _candidate().model_dump()
    values["recent_consecutivity"] = -1

    with pytest.raises(ValidationError):
        WorkforceCandidateSnapshot(**values)


def test_assigned_time_known_requires_value_and_unit():
    assigned_time = AssignedTimeSnapshot(
        status=AssignedTimeStatus.KNOWN,
        value=Decimal("8"),
        unit=AssignedTimeUnit.HOURS,
    )

    assert assigned_time.status == AssignedTimeStatus.KNOWN
    assert assigned_time.value == Decimal("8")
    assert assigned_time.unit == AssignedTimeUnit.HOURS

    with pytest.raises(ValidationError, match="requires value and unit"):
        AssignedTimeSnapshot(status=AssignedTimeStatus.KNOWN)


def test_assigned_time_unknown_does_not_invent_zero():
    assigned_time = AssignedTimeSnapshot(status=AssignedTimeStatus.UNKNOWN)

    assert assigned_time.value is None
    assert assigned_time.unit is None


@pytest.mark.parametrize(
    "payload",
    [
        {"value": Decimal("0")},
        {"unit": AssignedTimeUnit.MINUTES},
        {"value": Decimal("0"), "unit": AssignedTimeUnit.MINUTES},
    ],
)
def test_assigned_time_unknown_rejects_quantity_or_unit(payload):
    with pytest.raises(ValidationError, match="cannot include value or unit"):
        AssignedTimeSnapshot(status=AssignedTimeStatus.UNKNOWN, **payload)


def test_assigned_time_partial_preserves_known_incomplete_quantity():
    assigned_time = AssignedTimeSnapshot(
        status=AssignedTimeStatus.PARTIAL,
        value=Decimal("90"),
        unit=AssignedTimeUnit.MINUTES,
    )

    assert assigned_time.status == AssignedTimeStatus.PARTIAL
    assert assigned_time.value == Decimal("90")
    assert assigned_time.unit == AssignedTimeUnit.MINUTES


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"value": Decimal("90")},
        {"unit": AssignedTimeUnit.MINUTES},
    ],
)
def test_assigned_time_partial_requires_known_quantity_and_unit(payload):
    with pytest.raises(ValidationError, match="requires value and unit"):
        AssignedTimeSnapshot(status=AssignedTimeStatus.PARTIAL, **payload)


def test_existing_assigned_time_constructor_retains_known_semantics():
    assigned_time = AssignedTimeSnapshot(
        value=Decimal("0"), unit=AssignedTimeUnit.MINUTES
    )

    assert assigned_time.status == AssignedTimeStatus.KNOWN


def test_complete_current_member_contract_state_is_representable():
    contract_state = _candidate().applicable_contract_state

    assert contract_state.source_kind == (
        ContractStateSourceKind.CURRENT_MEMBER_CONTRACT_STATE
    )
    assert contract_state.employment_type == "full-time"
    assert contract_state.contract_start == date(2026, 1, 1)
    assert contract_state.contract_end == date(2026, 12, 31)
    assert contract_state.weekly_hours == Decimal("40")
    assert contract_state.is_reserve is False


def test_partial_contract_state_does_not_invent_missing_values():
    contract_state = CurrentMemberContractStateSnapshot(
        employment_type="part-time",
        weekly_hours=Decimal("24"),
    )

    assert contract_state.employment_type == "part-time"
    assert contract_state.weekly_hours == Decimal("24")
    assert contract_state.contract_start is None
    assert contract_state.contract_end is None
    assert contract_state.is_reserve is None


def test_absent_contract_data_is_representable_without_defaults():
    contract_state = CurrentMemberContractStateSnapshot()

    assert contract_state.employment_type is None
    assert contract_state.contract_start is None
    assert contract_state.contract_end is None
    assert contract_state.weekly_hours is None
    assert contract_state.is_reserve is None


def test_incoherent_contract_period_is_rejected():
    with pytest.raises(ValidationError, match="contract_end cannot precede"):
        CurrentMemberContractStateSnapshot(
            contract_start=date(2026, 12, 31),
            contract_end=date(2026, 1, 1),
        )


def test_negative_weekly_hours_is_rejected():
    with pytest.raises(ValidationError):
        CurrentMemberContractStateSnapshot(weekly_hours=Decimal("-1"))


@pytest.mark.parametrize("employment_type", ["", "   "])
def test_blank_employment_type_is_rejected(employment_type):
    with pytest.raises(ValidationError):
        CurrentMemberContractStateSnapshot(employment_type=employment_type)


@pytest.mark.parametrize("is_reserve", [0, 1, "true"])
def test_is_reserve_is_strict_when_present(is_reserve):
    with pytest.raises(ValidationError):
        CurrentMemberContractStateSnapshot(is_reserve=is_reserve)


def test_new_domain_contains_no_vertical_or_fleet_terminology():
    domain_file = (
        Path(__file__).parents[1]
        / "app"
        / "domain"
        / "workforce_auto_planning"
        / "weekly_planning_input_snapshot.py"
    )
    source = domain_file.read_text(encoding="utf-8").lower()

    forbidden_terms = (
        "amazon",
        "dsp",
        "next_day",
        "same_day",
        "operational_cycle",
        "fleet",
        "vehicle",
    )
    assert all(term not in source for term in forbidden_terms)
