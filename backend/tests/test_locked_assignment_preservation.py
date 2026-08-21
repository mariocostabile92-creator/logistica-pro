from datetime import date, datetime, timezone
from inspect import getsource

import pytest
from pydantic import ValidationError

from app.domain.core_language import OperationalUnit, TimeWindow
from app.domain.workforce_auto_planning import (
    AppliedPolicyMetadata,
    ComposedWeeklyWorkforceProposal,
    LockedAssignmentConflictStatus,
    LockedAssignmentDuplicateIdentityError,
    LockedAssignmentScopeMismatchError,
    LockedAssignmentUnknownDemandTraceError,
    OperationalDemand,
    ProposedAssignmentReason,
    ProposedShiftAssignment,
    ProposedShiftAssignmentOrigin,
    ProposedShiftAssignmentStatus,
    WeeklyPlanningInputSnapshot,
    WeeklyWorkforceProposal,
    WeeklyWorkforceProposalStatus,
    build_locked_assignment_preservation_set,
    compute_operational_demand_trace_id,
)
from app.domain.workforce_auto_planning import locked_assignment_preservation


ORGANIZATION_ID = "organization-one"
UNIT = OperationalUnit(external_identifier="unit-one", name="Unit one")
OTHER_UNIT = OperationalUnit(external_identifier="unit-two")
DAY_ONE = date(2026, 8, 24)
DAY_TWO = date(2026, 8, 25)
PERIOD_END = date(2026, 8, 30)
CREATED_AT = datetime(2026, 8, 23, 10, tzinfo=timezone.utc)


def _window(
    identifier: str = "window-one",
    *,
    starts_at: str | None = "08:00",
    ends_at: str | None = "12:00",
) -> TimeWindow:
    return TimeWindow(
        external_identifier=identifier,
        starts_at=starts_at,
        ends_at=ends_at,
    )


def _demand(
    *,
    target_quantity: int = 5,
    operational_date: date = DAY_ONE,
    window: TimeWindow | None = None,
    source: str = "normalized-source",
) -> OperationalDemand:
    return OperationalDemand(
        organization_id=ORGANIZATION_ID,
        operational_unit=UNIT,
        date=operational_date,
        time_window=window if window is not None else _window(),
        capability_or_workload="opaque-capability",
        base_quantity=target_quantity,
        target_quantity=target_quantity,
        source=source,
        applied_policy=AppliedPolicyMetadata(identifier="policy-rule"),
    )


def _snapshot(
    *,
    demands: tuple[OperationalDemand, ...] | None = None,
) -> WeeklyPlanningInputSnapshot:
    return WeeklyPlanningInputSnapshot(
        snapshot_id="snapshot-new",
        organization_id=ORGANIZATION_ID,
        period_start=DAY_ONE,
        period_end=PERIOD_END,
        operational_unit=UNIT,
        demands=demands if demands is not None else (_demand(),),
        workforce_candidates=(),
        policy_set_identifier="policy-set",
        policy_set_version="2",
        created_at=CREATED_AT,
        fingerprint="fingerprint-new",
    )


def _assignment(
    identifier: str,
    *,
    demand: OperationalDemand | None = None,
    locked: bool = True,
    member_id: str = "member-one",
    operational_date: date | None = None,
    organization_id: str = ORGANIZATION_ID,
    operational_unit: OperationalUnit = UNIT,
    window: TimeWindow | None = None,
    origin: ProposedShiftAssignmentOrigin = (
        ProposedShiftAssignmentOrigin.AUTOMATIC
    ),
) -> ProposedShiftAssignment:
    selected_demand = demand if demand is not None else _demand()
    return ProposedShiftAssignment(
        assignment_id=identifier,
        demand_trace_id=compute_operational_demand_trace_id(selected_demand),
        organization_id=organization_id,
        workforce_member_id=member_id,
        date=(
            operational_date
            if operational_date is not None
            else selected_demand.date
        ),
        operational_unit=operational_unit,
        shift_identifier="shift-one",
        time_window=window if window is not None else selected_demand.time_window,
        capability_or_workload=selected_demand.capability_or_workload,
        origin=origin,
        status=ProposedShiftAssignmentStatus.PROPOSED,
        deterministic_priority=0,
        reasons=(
            ProposedAssignmentReason(
                code="preserved-decision",
                message="Existing proposal assignment.",
            ),
        ),
        locked=locked,
    )


def _previous(
    assignments: tuple[ProposedShiftAssignment, ...] = (),
) -> ComposedWeeklyWorkforceProposal:
    return ComposedWeeklyWorkforceProposal(
        proposal=WeeklyWorkforceProposal(
            proposal_id="proposal-one",
            organization_id=ORGANIZATION_ID,
            period_start=DAY_ONE,
            period_end=PERIOD_END,
            operational_unit=UNIT,
            version=3,
            input_snapshot_id="snapshot-old",
            input_fingerprint="fingerprint-old",
            policy_set_identifier="policy-set",
            policy_set_version="1",
            status=WeeklyWorkforceProposalStatus.GENERATED,
            created_at=CREATED_AT,
        ),
        assignments=assignments,
        coverage_gaps=(),
        eligibility_decisions=(),
        preference_sets=(),
        ranked_candidates=(),
    )


def _build(
    assignments: tuple[ProposedShiftAssignment, ...] = (),
    *,
    snapshot: WeeklyPlanningInputSnapshot | None = None,
):
    return build_locked_assignment_preservation_set(
        previous=_previous(assignments),
        snapshot=snapshot if snapshot is not None else _snapshot(),
    )


def test_no_locked_assignments_produces_empty_preservation_set() -> None:
    result = _build()

    assert result.assignments == ()
    assert result.coverage_by_demand == ()
    assert result.workforce_member_ids == ()
    assert result.demand_trace_ids == ()
    assert result.conflicts == ()


def test_unlocked_assignment_is_excluded() -> None:
    result = _build((_assignment("assignment-one", locked=False),))

    assert result.assignments == ()


@pytest.mark.parametrize(
    "origin",
    (
        ProposedShiftAssignmentOrigin.AUTOMATIC,
        ProposedShiftAssignmentOrigin.MANUAL,
    ),
)
def test_locked_assignment_is_included_regardless_of_origin(
    origin: ProposedShiftAssignmentOrigin,
) -> None:
    assignment = _assignment("assignment-one", origin=origin)

    result = _build((assignment,))

    assert result.assignments == (assignment,)
    assert result.assignments[0].origin is origin


def test_unknown_demand_trace_is_rejected() -> None:
    assignment = _assignment("assignment-one").model_copy(
        update={"demand_trace_id": "unknown-trace"}
    )

    with pytest.raises(LockedAssignmentUnknownDemandTraceError):
        _build((assignment,))


@pytest.mark.parametrize(
    "assignment",
    (
        _assignment("assignment-one", organization_id="organization-two"),
        _assignment("assignment-one", operational_date=date(2026, 8, 31)),
        _assignment("assignment-one", operational_unit=OTHER_UNIT),
    ),
)
def test_structural_scope_mismatch_is_rejected(
    assignment: ProposedShiftAssignment,
) -> None:
    with pytest.raises(LockedAssignmentScopeMismatchError):
        _build((assignment,))


@pytest.mark.parametrize(
    ("locked_count", "remaining", "overcoverage"),
    ((2, 3, 0), (5, 0, 0), (7, 0, 2)),
)
def test_locked_coverage_is_calculated_from_demand_target(
    locked_count: int,
    remaining: int,
    overcoverage: int,
) -> None:
    demand = _demand(target_quantity=5)
    assignments = tuple(
        _assignment(
            f"assignment-{index}",
            demand=demand,
            member_id=f"member-{index}",
        )
        for index in range(locked_count)
    )

    result = _build(assignments, snapshot=_snapshot(demands=(demand,)))
    coverage = result.coverage_by_demand[0]

    assert coverage.locked_assignments_count == locked_count
    assert coverage.target_quantity == 5
    assert coverage.remaining_quantity == remaining
    assert coverage.overcoverage_quantity == overcoverage
    assert len(result.assignments) == locked_count


def test_non_overlapping_locked_assignments_are_preserved_without_conflict() -> None:
    first = _assignment(
        "assignment-one",
        window=_window("window-a", starts_at="08:00", ends_at="10:00"),
    )
    second = _assignment(
        "assignment-two",
        window=_window("window-b", starts_at="10:30", ends_at="12:00"),
    )

    result = _build((second, first))

    assert len(result.assignments) == 2
    assert result.conflicts == ()


def test_overlapping_locked_assignments_are_preserved_with_conflict() -> None:
    first = _assignment(
        "assignment-one",
        window=_window("window-a", starts_at="08:00", ends_at="11:00"),
    )
    second = _assignment(
        "assignment-two",
        window=_window("window-b", starts_at="10:00", ends_at="12:00"),
    )

    result = _build((second, first))

    assert len(result.assignments) == 2
    assert len(result.conflicts) == 1
    assert result.conflicts[0].status is LockedAssignmentConflictStatus.CONFLICT
    assert result.conflicts[0].assignment_ids == (
        "assignment-one",
        "assignment-two",
    )


def test_touching_boundary_is_not_a_conflict() -> None:
    first = _assignment(
        "assignment-one",
        window=_window("window-a", starts_at="08:00", ends_at="10:00"),
    )
    second = _assignment(
        "assignment-two",
        window=_window("window-b", starts_at="10:00", ends_at="12:00"),
    )

    result = _build((first, second))

    assert result.conflicts == ()


@pytest.mark.parametrize(
    "uncertain_window",
    (
        _window("window-incomplete", starts_at=None, ends_at="12:00"),
        _window("window-invalid", starts_at="not-a-time", ends_at="12:00"),
        _window("window-overnight", starts_at="20:00", ends_at="08:00"),
    ),
)
def test_incomplete_or_invalid_window_produces_uncertainty_evidence(
    uncertain_window: TimeWindow,
) -> None:
    first = _assignment("assignment-one", window=uncertain_window)
    second = _assignment(
        "assignment-two",
        window=_window("window-valid", starts_at="10:00", ends_at="12:00"),
    )

    result = _build((first, second))

    assert len(result.assignments) == 2
    assert len(result.conflicts) == 1
    assert result.conflicts[0].status is LockedAssignmentConflictStatus.UNKNOWN
    assert result.conflicts[0].reason.code == "locked-time-window-uncertain"


def test_assignments_on_different_dates_do_not_conflict() -> None:
    demand_one = _demand()
    demand_two = _demand(
        operational_date=DAY_TWO,
        window=_window("window-two"),
    )
    first = _assignment("assignment-one", demand=demand_one)
    second = _assignment("assignment-two", demand=demand_two)

    result = _build(
        (first, second),
        snapshot=_snapshot(demands=(demand_one, demand_two)),
    )

    assert result.conflicts == ()


def test_business_eligibility_is_not_required_for_preservation() -> None:
    assignment = _assignment(
        "assignment-one",
        member_id="member-not-present-in-snapshot",
    )

    result = _build((assignment,))

    assert result.assignments == (assignment,)


def test_duplicate_locked_assignment_identity_is_rejected() -> None:
    first = _assignment("duplicate-id", member_id="member-one")
    second = _assignment("duplicate-id", member_id="member-two")

    with pytest.raises(LockedAssignmentDuplicateIdentityError):
        _build((first, second))


def test_output_ordering_is_deterministic() -> None:
    demand_one = _demand(source="source-z")
    demand_two = _demand(
        operational_date=DAY_TWO,
        window=_window("window-two"),
        source="source-a",
    )
    values = (
        _assignment(
            "assignment-z",
            demand=demand_two,
            member_id="member-z",
        ),
        _assignment(
            "assignment-b",
            demand=demand_one,
            member_id="member-b",
        ),
        _assignment(
            "assignment-a",
            demand=demand_one,
            member_id="member-a",
        ),
    )
    snapshot = _snapshot(demands=(demand_two, demand_one))

    first = _build(values, snapshot=snapshot)
    second = _build(tuple(reversed(values)), snapshot=snapshot)

    assert first == second
    assert [item.assignment_id for item in first.assignments] == [
        "assignment-a",
        "assignment-b",
        "assignment-z",
    ]
    assert first.workforce_member_ids == (
        "member-a",
        "member-b",
        "member-z",
    )
    assert first.demand_trace_ids == tuple(sorted(first.demand_trace_ids))
    assert [item.demand_trace_id for item in first.coverage_by_demand] == list(
        sorted(first.demand_trace_ids)
    )


def test_previous_snapshot_and_assignments_are_not_mutated() -> None:
    assignment = _assignment("assignment-one")
    previous = _previous((assignment,))
    snapshot = _snapshot()
    previous_before = previous.model_dump(mode="json")
    snapshot_before = snapshot.model_dump(mode="json")
    assignment_before = assignment.model_dump(mode="json")

    build_locked_assignment_preservation_set(
        previous=previous,
        snapshot=snapshot,
    )

    assert previous.model_dump(mode="json") == previous_before
    assert snapshot.model_dump(mode="json") == snapshot_before
    assert assignment.model_dump(mode="json") == assignment_before


def test_output_is_immutable() -> None:
    result = _build((_assignment("assignment-one"),))

    with pytest.raises(ValidationError):
        result.assignments = ()
    with pytest.raises(ValidationError):
        result.coverage_by_demand[0].remaining_quantity = 99


def test_preservation_does_not_generate_query_or_persist() -> None:
    source = getsource(locked_assignment_preservation)

    assert "generate_weekly_proposal_baseline" not in source
    assert "evaluate_workforce_candidate_eligibility" not in source
    assert "repository" not in source.casefold()
    assert "sqlalchemy" not in source.casefold()
    assert "fastapi" not in source.casefold()
