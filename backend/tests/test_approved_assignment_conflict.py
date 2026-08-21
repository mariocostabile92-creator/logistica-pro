from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.core_language import OperationalUnit, TimeWindow
from app.domain.workforce_auto_planning import (
    ApprovedAssignmentConflictEvaluation,
    ApprovedAssignmentConflictStatus,
    ApprovedAssignmentSnapshot,
    AppliedPolicyMetadata,
    AssignedTimeSnapshot,
    AssignedTimeStatus,
    AssignedTimeUnit,
    OperationalDemand,
    evaluate_approved_assignment_conflict,
)


OPERATION_DATE = date(2026, 8, 24)
UNIT = OperationalUnit(external_identifier="unit-north")
OTHER_UNIT = OperationalUnit(external_identifier="unit-south")


def _window(
    start: str | None,
    end: str | None,
    *,
    identifier: str,
) -> TimeWindow:
    return TimeWindow(
        external_identifier=identifier,
        starts_at=start,
        ends_at=end,
    )


def _assignment(
    *,
    operation_date: date = OPERATION_DATE,
    start: str | None = "08:00",
    end: str | None = "12:00",
    operational_unit: OperationalUnit | None = UNIT,
    shift_identifier: str | None = "C1",
) -> ApprovedAssignmentSnapshot:
    return ApprovedAssignmentSnapshot(
        assignment_reference="approved-assignment-1",
        date=operation_date,
        operational_unit=operational_unit,
        shift_identifier=shift_identifier,
        time_window=_window(start, end, identifier="assignment-window"),
        assigned_time=AssignedTimeSnapshot(
            status=AssignedTimeStatus.KNOWN,
            value=Decimal("240"),
            unit=AssignedTimeUnit.MINUTES,
        ),
    )


def _demand(
    *,
    operation_date: date = OPERATION_DATE,
    start: str | None = "12:00",
    end: str | None = "16:00",
) -> OperationalDemand:
    return OperationalDemand(
        organization_id="organization-one",
        operational_unit=UNIT,
        date=operation_date,
        time_window=_window(start, end, identifier="demand-window"),
        capability_or_workload="generic-capability",
        base_quantity=1,
        target_quantity=1,
        source="normalized-demand",
        applied_policy=AppliedPolicyMetadata(identifier="baseline-policy"),
    )


def _evaluate(
    *,
    assignment: ApprovedAssignmentSnapshot | None = None,
    demand: OperationalDemand | None = None,
) -> ApprovedAssignmentConflictEvaluation:
    return evaluate_approved_assignment_conflict(
        assignment=assignment or _assignment(),
        demand=demand or _demand(),
    )


def test_different_dates_have_no_conflict_without_time_comparison():
    result = _evaluate(
        assignment=_assignment(
            operation_date=date(2026, 8, 23),
            start=None,
            end=None,
        )
    )

    assert result.status == ApprovedAssignmentConflictStatus.NO_CONFLICT
    assert result.reason.code == "different-date"


def test_adjacent_half_open_intervals_do_not_overlap():
    result = _evaluate()

    assert result.status == ApprovedAssignmentConflictStatus.NO_CONFLICT
    assert result.reason.code == "no-overlap"


def test_one_minute_overlap_is_a_conflict():
    result = _evaluate(demand=_demand(start="11:59", end="16:00"))

    assert result.status == ApprovedAssignmentConflictStatus.CONFLICT
    assert result.reason.code == "overlapping-time-window"


def test_contained_interval_is_a_conflict():
    result = _evaluate(demand=_demand(start="09:00", end="10:00"))

    assert result.status == ApprovedAssignmentConflictStatus.CONFLICT


def test_identical_intervals_are_a_conflict():
    result = _evaluate(demand=_demand(start="08:00", end="12:00"))

    assert result.status == ApprovedAssignmentConflictStatus.CONFLICT


@pytest.mark.parametrize(
    ("assignment_start", "assignment_end", "demand_start", "demand_end"),
    [
        (None, "12:00", "12:00", "16:00"),
        ("08:00", None, "12:00", "16:00"),
        ("08:00", "12:00", None, "16:00"),
        ("08:00", "12:00", "12:00", None),
    ],
)
def test_missing_time_endpoint_is_unknown(
    assignment_start,
    assignment_end,
    demand_start,
    demand_end,
):
    result = _evaluate(
        assignment=_assignment(start=assignment_start, end=assignment_end),
        demand=_demand(start=demand_start, end=demand_end),
    )

    assert result.status == ApprovedAssignmentConflictStatus.UNKNOWN
    assert result.reason.code == "incomplete-time-window"


@pytest.mark.parametrize(
    ("assignment_start", "assignment_end", "demand_start", "demand_end"),
    [
        ("12:00", "12:00", "12:00", "16:00"),
        ("12:01", "12:00", "12:00", "16:00"),
        ("08:00", "12:00", "16:00", "16:00"),
        ("08:00", "12:00", "16:01", "16:00"),
    ],
)
def test_end_not_after_start_is_unknown(
    assignment_start,
    assignment_end,
    demand_start,
    demand_end,
):
    result = _evaluate(
        assignment=_assignment(start=assignment_start, end=assignment_end),
        demand=_demand(start=demand_start, end=demand_end),
    )

    assert result.status == ApprovedAssignmentConflictStatus.UNKNOWN
    assert result.reason.code == "unsupported-time-window"


def test_assignment_without_operational_unit_remains_valid():
    result = _evaluate(assignment=_assignment(operational_unit=None))
    evidence = {item.key: item.value for item in result.evidence}

    assert result.status == ApprovedAssignmentConflictStatus.NO_CONFLICT
    assert evidence["assignment-operational-unit"] is None


def test_assignment_from_another_unit_can_still_conflict():
    result = _evaluate(
        assignment=_assignment(operational_unit=OTHER_UNIT),
        demand=_demand(start="11:00", end="16:00"),
    )

    assert result.status == ApprovedAssignmentConflictStatus.CONFLICT


def test_missing_shift_identifier_remains_valid_and_does_not_infer_time():
    result = _evaluate(
        assignment=_assignment(
            start=None,
            end=None,
            shift_identifier=None,
        )
    )
    evidence = {item.key: item.value for item in result.evidence}

    assert result.status == ApprovedAssignmentConflictStatus.UNKNOWN
    assert result.reason.code == "incomplete-time-window"
    assert evidence["assignment-shift-identifier"] is None


def test_shift_identifier_does_not_supply_missing_time_information():
    result = _evaluate(
        assignment=_assignment(
            start=None,
            end=None,
            shift_identifier="C1",
        )
    )

    assert result.status == ApprovedAssignmentConflictStatus.UNKNOWN


def test_overnight_intervals_are_not_interpreted():
    result = _evaluate(
        assignment=_assignment(start="22:00", end="06:00")
    )

    assert result.status == ApprovedAssignmentConflictStatus.UNKNOWN
    assert result.reason.code == "unsupported-time-window"


def test_result_is_deterministic_and_inputs_are_not_mutated():
    assignment = _assignment()
    demand = _demand(start="11:00", end="16:00")
    assignment_before = assignment.model_dump(mode="json")
    demand_before = demand.model_dump(mode="json")

    first = _evaluate(assignment=assignment, demand=demand)
    second = _evaluate(assignment=assignment, demand=demand)

    assert first == second
    assert assignment.model_dump(mode="json") == assignment_before
    assert demand.model_dump(mode="json") == demand_before


def test_conflict_models_are_immutable():
    result = _evaluate()

    with pytest.raises(ValidationError):
        result.status = ApprovedAssignmentConflictStatus.CONFLICT
    with pytest.raises(ValidationError):
        result.reason.code = "changed"
    with pytest.raises(TypeError):
        result.evidence[0] = result.evidence[0]


def test_conflict_module_has_no_external_or_out_of_scope_dependencies():
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "domain"
        / "workforce_auto_planning"
        / "approved_assignment_conflict.py"
    ).read_text(encoding="utf-8").casefold()

    forbidden_fragments = (
        "plugins.",
        "repository",
        "sqlalchemy",
        "fastapi",
        "weekly_hours",
        "recent_consecutivity",
        "candidate.capabilities",
    )
    assert all(fragment not in source for fragment in forbidden_fragments)
