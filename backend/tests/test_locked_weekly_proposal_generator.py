from datetime import date, datetime, timezone
from decimal import Decimal
from inspect import getsource
from unittest.mock import Mock

from app.domain.core_language import (
    HumanResource,
    OperationalUnit,
    ResourceAvailability,
    ResourceKind,
    TimeWindow,
)
from app.domain.workforce_auto_planning import (
    AppliedPolicyMetadata,
    AssignedTimeSnapshot,
    AssignedTimeStatus,
    AssignedTimeUnit,
    CandidateOperationalUnitScope,
    CandidateOperationalUnitScopeStatus,
    ComposedWeeklyWorkforceProposal,
    CurrentMemberContractStateSnapshot,
    OperationalDemand,
    ProposedAssignmentReason,
    ProposedShiftAssignment,
    ProposedShiftAssignmentOrigin,
    ProposedShiftAssignmentStatus,
    WeeklyPlanningInputSnapshot,
    WeeklyWorkforceProposal,
    WeeklyWorkforceProposalStatus,
    WorkforceCandidateAvailabilitySnapshot,
    WorkforceCandidateSnapshot,
    WorkloadCapabilityMapping,
    compute_operational_demand_trace_id,
    generate_weekly_proposal_preserving_locked,
)
from app.domain.workforce_auto_planning import locked_weekly_proposal_generator


ORGANIZATION_ID = "organization-one"
UNIT = OperationalUnit(external_identifier="unit-one")
DAY_ONE = date(2026, 8, 24)
DAY_TWO = date(2026, 8, 25)
CREATED_AT = datetime(2026, 8, 20, 8, tzinfo=timezone.utc)
CAPABILITY = "opaque-capability"
MAPPINGS = (
    WorkloadCapabilityMapping(
        workload_identifier=CAPABILITY,
        required_capabilities=(CAPABILITY,),
    ),
)


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
    target_quantity: int = 1,
    operational_date: date = DAY_ONE,
    window: TimeWindow | None = None,
    source: str = "normalized-source",
) -> OperationalDemand:
    return OperationalDemand(
        organization_id=ORGANIZATION_ID,
        operational_unit=UNIT,
        date=operational_date,
        time_window=window if window is not None else _window(),
        capability_or_workload=CAPABILITY,
        base_quantity=target_quantity,
        target_quantity=target_quantity,
        source=source,
        applied_policy=AppliedPolicyMetadata(identifier="policy-rule"),
    )


def _candidate(
    identifier: str,
    *,
    callable_on_dates: tuple[date, ...] = (DAY_ONE, DAY_TWO),
    capabilities: tuple[str, ...] = (CAPABILITY,),
    weekly_hours: Decimal | None = Decimal("40"),
    assigned_minutes: Decimal = Decimal("0"),
) -> WorkforceCandidateSnapshot:
    return WorkforceCandidateSnapshot(
        organization_id=ORGANIZATION_ID,
        human_resource=HumanResource(
            external_identifier=identifier,
            capabilities=capabilities,
        ),
        availability=tuple(
            WorkforceCandidateAvailabilitySnapshot(
                date=operational_date,
                availability=ResourceAvailability(
                    resource_identifier=identifier,
                    resource_kind=ResourceKind.HUMAN_RESOURCE,
                    available=True,
                    observed_state="available",
                ),
            )
            for operational_date in callable_on_dates
        ),
        applicable_contract_state=CurrentMemberContractStateSnapshot(
            weekly_hours=weekly_hours
        ),
        operational_unit_scope=CandidateOperationalUnitScope(
            status=CandidateOperationalUnitScopeStatus.MATCHED,
            requested_unit=UNIT,
            candidate_unit=UNIT,
        ),
        recent_consecutivity=0,
        already_assigned_minutes_or_hours=AssignedTimeSnapshot(
            status=AssignedTimeStatus.KNOWN,
            value=assigned_minutes,
            unit=AssignedTimeUnit.MINUTES,
        ),
    )


def _snapshot(
    *,
    demands: tuple[OperationalDemand, ...],
    candidates: tuple[WorkforceCandidateSnapshot, ...] = (),
) -> WeeklyPlanningInputSnapshot:
    return WeeklyPlanningInputSnapshot(
        snapshot_id="snapshot-new",
        organization_id=ORGANIZATION_ID,
        period_start=DAY_ONE,
        period_end=DAY_TWO,
        operational_unit=UNIT,
        demands=demands,
        workforce_candidates=candidates,
        policy_set_identifier="policy-set",
        policy_set_version="2",
        created_at=CREATED_AT,
        fingerprint="fingerprint-new",
    )


def _assignment(
    identifier: str,
    *,
    demand: OperationalDemand,
    member_id: str,
    locked: bool = True,
    window: TimeWindow | None = None,
    origin: ProposedShiftAssignmentOrigin = ProposedShiftAssignmentOrigin.MANUAL,
    status: ProposedShiftAssignmentStatus = ProposedShiftAssignmentStatus.ACCEPTED,
    deterministic_priority: int = 17,
) -> ProposedShiftAssignment:
    return ProposedShiftAssignment(
        assignment_id=identifier,
        demand_trace_id=compute_operational_demand_trace_id(demand),
        organization_id=ORGANIZATION_ID,
        workforce_member_id=member_id,
        date=demand.date,
        operational_unit=UNIT,
        shift_identifier="dispatcher-shift",
        time_window=window if window is not None else demand.time_window,
        capability_or_workload=demand.capability_or_workload,
        origin=origin,
        status=status,
        deterministic_priority=deterministic_priority,
        reasons=(
            ProposedAssignmentReason(
                code="dispatcher-decision",
                message="Preserve this dispatcher decision.",
            ),
        ),
        locked=locked,
    )


def _previous(
    assignments: tuple[ProposedShiftAssignment, ...],
) -> ComposedWeeklyWorkforceProposal:
    return ComposedWeeklyWorkforceProposal(
        proposal=WeeklyWorkforceProposal(
            proposal_id="proposal-one",
            organization_id=ORGANIZATION_ID,
            period_start=DAY_ONE,
            period_end=DAY_TWO,
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


def _factory(**values: object) -> str:
    operational_date = values["operational_date"]
    time_window = values["time_window"]
    return (
        f"new:{operational_date.isoformat()}:"
        f"{time_window.external_identifier}:"
        f"{values['workforce_member_id']}"
    )


def _generate(
    *,
    snapshot: WeeklyPlanningInputSnapshot,
    previous: ComposedWeeklyWorkforceProposal,
    factory=_factory,
):
    return generate_weekly_proposal_preserving_locked(
        snapshot=snapshot,
        previous=previous,
        capability_mappings=MAPPINGS,
        existing_assignment_stability_priority=0,
        lower_weekly_load_priority=1,
        continuity_priority=2,
        assignment_id_factory=factory,
    )


def _gap(result, demand: OperationalDemand):
    trace = compute_operational_demand_trace_id(demand)
    return next(item for item in result.coverage_gaps if item.demand_trace_id == trace)


def test_locked_assignment_is_preserved_exactly_without_factory_call() -> None:
    demand = _demand(target_quantity=1)
    locked = _assignment("locked-one", demand=demand, member_id="member-locked")
    factory = Mock(side_effect=AssertionError("factory must not handle locked"))

    result = _generate(
        snapshot=_snapshot(demands=(demand,)),
        previous=_previous((locked,)),
        factory=factory,
    )

    assert result.assignments == (locked,)
    assert result.assignments[0].model_dump() == locked.model_dump()
    factory.assert_not_called()


def test_unlocked_previous_assignment_is_not_automatically_preserved() -> None:
    demand = _demand(target_quantity=1)
    unlocked = _assignment(
        "old-unlocked",
        demand=demand,
        member_id="member-a",
        locked=False,
    )

    result = _generate(
        snapshot=_snapshot(demands=(demand,), candidates=(_candidate("member-a"),)),
        previous=_previous((unlocked,)),
    )

    assert all(item.assignment_id != "old-unlocked" for item in result.assignments)
    assert [item.assignment_id for item in result.assignments] == [
        "new:2026-08-24:window-one:member-a"
    ]


def test_target_five_with_two_locked_generates_only_three() -> None:
    demand = _demand(target_quantity=5)
    locked = tuple(
        _assignment(
            f"locked-{index}",
            demand=demand,
            member_id=f"locked-member-{index}",
        )
        for index in range(2)
    )
    candidates = tuple(_candidate(f"member-{index}") for index in range(3))

    result = _generate(
        snapshot=_snapshot(demands=(demand,), candidates=candidates),
        previous=_previous(locked),
    )

    assert sum(item.locked for item in result.assignments) == 2
    assert sum(not item.locked for item in result.assignments) == 3
    assert _gap(result, demand).proposed_quantity == 5
    assert _gap(result, demand).gap_quantity == 0


def test_target_five_fully_consumed_by_locked_generates_zero() -> None:
    demand = _demand(target_quantity=5)
    locked = tuple(
        _assignment(
            f"locked-{index}",
            demand=demand,
            member_id=f"locked-member-{index}",
        )
        for index in range(5)
    )
    factory = Mock(side_effect=AssertionError("residual is zero"))

    result = _generate(
        snapshot=_snapshot(demands=(demand,), candidates=(_candidate("member-a"),)),
        previous=_previous(locked),
        factory=factory,
    )

    assert result.assignments == locked
    assert result.eligibility_decisions == ()
    assert result.preference_sets == ()
    assert result.ranked_candidates == ()
    assert _gap(result, demand).gap_quantity == 0
    factory.assert_not_called()


def test_locked_overcoverage_is_preserved_with_negative_gap() -> None:
    demand = _demand(target_quantity=5)
    locked = tuple(
        _assignment(
            f"locked-{index}",
            demand=demand,
            member_id=f"locked-member-{index}",
        )
        for index in range(7)
    )

    result = _generate(
        snapshot=_snapshot(demands=(demand,)),
        previous=_previous(locked),
    )
    gap = _gap(result, demand)

    assert len(result.assignments) == 7
    assert gap.required_quantity == 5
    assert gap.proposed_quantity == 7
    assert gap.gap_quantity == -2
    assert gap.reason.code == "locked-overcoverage"
    assert "locked overcoverage: 2" in gap.reason.message


def test_overlapping_locked_driver_is_skipped_and_next_ranked_is_used() -> None:
    demand = _demand(target_quantity=2)
    locked = _assignment("locked-one", demand=demand, member_id="member-a")

    result = _generate(
        snapshot=_snapshot(
            demands=(demand,),
            candidates=(_candidate("member-a"), _candidate("member-b")),
        ),
        previous=_previous((locked,)),
    )

    assert [item.workforce_member_id for item in result.assignments] == [
        "member-a",
        "member-b",
    ]
    generated = next(item for item in result.assignments if not item.locked)
    assert generated.workforce_member_id == "member-b"
    assert "skipped for locked reservation: 1" in _gap(
        result, demand
    ).reason.message


def test_touching_locked_boundary_allows_same_driver() -> None:
    locked_demand = _demand(
        target_quantity=1,
        window=_window("early", starts_at="08:00", ends_at="10:00"),
        source="early-source",
    )
    new_demand = _demand(
        target_quantity=1,
        window=_window("late", starts_at="10:00", ends_at="12:00"),
        source="late-source",
    )
    locked = _assignment("locked-one", demand=locked_demand, member_id="member-a")

    result = _generate(
        snapshot=_snapshot(
            demands=(locked_demand, new_demand),
            candidates=(_candidate("member-a"),),
        ),
        previous=_previous((locked,)),
    )

    assert len(result.assignments) == 2
    assert {item.workforce_member_id for item in result.assignments} == {"member-a"}
    assert _gap(result, new_demand).gap_quantity == 0


def test_unknown_locked_window_blocks_same_driver_fail_closed() -> None:
    locked_demand = _demand(
        target_quantity=1,
        window=_window("unknown", starts_at=None, ends_at="10:00"),
        source="unknown-source",
    )
    new_demand = _demand(
        target_quantity=1,
        window=_window("valid", starts_at="10:00", ends_at="12:00"),
        source="valid-source",
    )
    locked = _assignment("locked-one", demand=locked_demand, member_id="member-a")

    result = _generate(
        snapshot=_snapshot(
            demands=(locked_demand, new_demand),
            candidates=(_candidate("member-a"), _candidate("member-b")),
        ),
        previous=_previous((locked,)),
    )

    generated = next(
        item
        for item in result.assignments
        if item.demand_trace_id == compute_operational_demand_trace_id(new_demand)
    )
    assert generated.workforce_member_id == "member-b"


def test_locked_reservation_on_different_date_does_not_block() -> None:
    locked_demand = _demand(target_quantity=1, operational_date=DAY_ONE)
    new_demand = _demand(
        target_quantity=1,
        operational_date=DAY_TWO,
        window=_window("day-two"),
    )
    locked = _assignment("locked-one", demand=locked_demand, member_id="member-a")

    result = _generate(
        snapshot=_snapshot(
            demands=(locked_demand, new_demand),
            candidates=(_candidate("member-a"),),
        ),
        previous=_previous((locked,)),
    )

    generated = next(item for item in result.assignments if not item.locked)
    assert generated.workforce_member_id == "member-a"
    assert generated.date == DAY_TWO


def test_new_assignments_use_full_eligibility_preferences_and_ranking() -> None:
    demand = _demand(target_quantity=1)
    non_callable = _candidate("member-a", callable_on_dates=())
    eligible = _candidate("member-b")

    result = _generate(
        snapshot=_snapshot(
            demands=(demand,),
            candidates=(non_callable, eligible),
        ),
        previous=_previous(()),
    )

    assert len(result.eligibility_decisions) == 2
    assert any(not item.eligible for item in result.eligibility_decisions)
    assert len(result.preference_sets) == 1
    assert len(result.ranked_candidates) == 1
    generated = result.assignments[0]
    assert generated.workforce_member_id == "member-b"
    assert generated.origin is ProposedShiftAssignmentOrigin.AUTOMATIC
    assert generated.locked is False
    assert generated.assignment_id.startswith("new:")
    assert generated.deterministic_priority == 1
    assert generated.demand_trace_id == compute_operational_demand_trace_id(demand)


def test_locked_business_failures_do_not_remove_assignment() -> None:
    demand = _demand(target_quantity=1)
    locked = _assignment("locked-one", demand=demand, member_id="member-a")
    invalid_candidate = _candidate(
        "member-a",
        callable_on_dates=(),
        capabilities=("wrong-capability",),
        weekly_hours=Decimal("0"),
    )

    result = _generate(
        snapshot=_snapshot(demands=(demand,), candidates=(invalid_candidate,)),
        previous=_previous((locked,)),
    )

    assert result.assignments == (locked,)
    assert result.eligibility_decisions == ()


def test_locked_conflict_between_locked_assignments_does_not_abort_run() -> None:
    demand = _demand(target_quantity=2)
    first = _assignment("locked-a", demand=demand, member_id="member-a")
    second = _assignment("locked-b", demand=demand, member_id="member-a")

    result = _generate(
        snapshot=_snapshot(demands=(demand,)),
        previous=_previous((second, first)),
    )

    assert [item.assignment_id for item in result.assignments] == [
        "locked-a",
        "locked-b",
    ]
    assert _gap(result, demand).gap_quantity == 0


def test_positive_gap_uses_locked_plus_generated_and_explains_counts() -> None:
    demand = _demand(target_quantity=3)
    locked = _assignment("locked-one", demand=demand, member_id="locked-member")

    result = _generate(
        snapshot=_snapshot(demands=(demand,), candidates=(_candidate("member-a"),)),
        previous=_previous((locked,)),
    )
    gap = _gap(result, demand)

    assert gap.proposed_quantity == 2
    assert gap.gap_quantity == 1
    assert "locked assignments: 1" in gap.reason.message
    assert "newly generated assignments: 1" in gap.reason.message
    assert "eligible cohort size: 1" in gap.reason.message


def test_previous_snapshot_and_locked_assignments_are_not_mutated() -> None:
    demand = _demand(target_quantity=2)
    locked = _assignment("locked-one", demand=demand, member_id="member-a")
    snapshot = _snapshot(
        demands=(demand,),
        candidates=(_candidate("member-a"), _candidate("member-b")),
    )
    previous = _previous((locked,))
    snapshot_before = snapshot.model_dump(mode="json")
    previous_before = previous.model_dump(mode="json")
    locked_before = locked.model_dump(mode="json")

    _generate(snapshot=snapshot, previous=previous)

    assert snapshot.model_dump(mode="json") == snapshot_before
    assert previous.model_dump(mode="json") == previous_before
    assert locked.model_dump(mode="json") == locked_before


def test_output_is_deterministic_for_reversed_inputs() -> None:
    first_demand = _demand(
        target_quantity=1,
        window=_window("window-a"),
        source="source-a",
    )
    second_demand = _demand(
        target_quantity=1,
        operational_date=DAY_TWO,
        window=_window("window-b"),
        source="source-b",
    )
    first_locked = _assignment(
        "locked-a",
        demand=first_demand,
        member_id="locked-a",
    )
    second_locked = _assignment(
        "locked-b",
        demand=second_demand,
        member_id="locked-b",
    )
    candidates = (_candidate("member-a"), _candidate("member-b"))

    first = _generate(
        snapshot=_snapshot(
            demands=(first_demand, second_demand),
            candidates=candidates,
        ),
        previous=_previous((first_locked, second_locked)),
    )
    second = _generate(
        snapshot=_snapshot(
            demands=(second_demand, first_demand),
            candidates=tuple(reversed(candidates)),
        ),
        previous=_previous((second_locked, first_locked)),
    )

    assert first == second


def test_generator_has_no_query_repository_persistence_or_runtime_side_effects() -> None:
    source = getsource(locked_weekly_proposal_generator)

    assert "db_session" not in source
    assert "repository" not in source.casefold()
    assert "sqlalchemy" not in source.casefold()
    assert "fastapi" not in source.casefold()
    assert "uuid" not in source.casefold()
