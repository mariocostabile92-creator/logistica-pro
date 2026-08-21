from datetime import date, datetime, timezone
from decimal import Decimal
from inspect import getsource

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
    AppliedPolicyMetadata,
    AssignedTimeSnapshot,
    AssignedTimeStatus,
    AssignedTimeUnit,
    CandidateOperationalUnitScope,
    CandidateOperationalUnitScopeStatus,
    ConstraintEvaluation,
    ConstraintEvaluationCategory,
    CurrentMemberContractStateSnapshot,
    DispatcherManualOverride,
    DispatcherOverrideOperationType,
    DispatcherWeeklyEditAssignmentNotFoundError,
    DispatcherWeeklyEditCommand,
    DispatcherWeeklyEditCommandMismatchError,
    DispatcherWeeklyEditScopeMismatchError,
    DispatcherWeeklyEditUnknownDemandTraceError,
    OperationalDemand,
    ProposedShiftAssignmentOrigin,
    ProposedShiftAssignmentStatus,
    WeeklyPlanningInputSnapshot,
    WeeklyWorkforceProposalStatus,
    WorkforceCandidateAvailabilitySnapshot,
    WorkforceCandidateSnapshot,
    WorkloadCapabilityMapping,
    apply_dispatcher_weekly_edit,
    compose_weekly_workforce_proposal,
    generate_weekly_proposal_baseline,
)
from app.domain.workforce_auto_planning import dispatcher_weekly_edit


ORGANIZATION_ID = "organization-one"
UNIT = OperationalUnit(external_identifier="unit-one", name="Unit one")
DAY_ONE = date(2026, 8, 24)
DAY_TWO = date(2026, 8, 25)
PERIOD_END = date(2026, 8, 30)
CREATED_AT = datetime(2026, 8, 23, 10, tzinfo=timezone.utc)
CAPABILITY = "opaque-capability"


def _window(day: int) -> TimeWindow:
    return TimeWindow(
        external_identifier=f"window-{day}",
        starts_at="08:00",
        ends_at="12:00",
    )


def _candidate() -> WorkforceCandidateSnapshot:
    return WorkforceCandidateSnapshot(
        organization_id=ORGANIZATION_ID,
        human_resource=HumanResource(
            external_identifier="member-original",
            capabilities=(CAPABILITY,),
        ),
        availability=tuple(
            WorkforceCandidateAvailabilitySnapshot(
                date=operational_date,
                availability=ResourceAvailability(
                    resource_identifier="member-original",
                    resource_kind=ResourceKind.HUMAN_RESOURCE,
                    available=True,
                    observed_state="available",
                ),
            )
            for operational_date in (DAY_ONE, DAY_TWO)
        ),
        applicable_contract_state=CurrentMemberContractStateSnapshot(
            weekly_hours=Decimal("40")
        ),
        operational_unit_scope=CandidateOperationalUnitScope(
            status=CandidateOperationalUnitScopeStatus.MATCHED,
            requested_unit=UNIT,
            candidate_unit=UNIT,
        ),
        recent_consecutivity=0,
        already_assigned_minutes_or_hours=AssignedTimeSnapshot(
            status=AssignedTimeStatus.KNOWN,
            value=Decimal("0"),
            unit=AssignedTimeUnit.MINUTES,
        ),
    )


def _previous():
    demands = tuple(
        OperationalDemand(
            organization_id=ORGANIZATION_ID,
            operational_unit=UNIT,
            date=operational_date,
            time_window=_window(index),
            capability_or_workload=CAPABILITY,
            base_quantity=1,
            target_quantity=1,
            source="normalized-source",
            applied_policy=AppliedPolicyMetadata(identifier="policy-rule"),
        )
        for index, operational_date in enumerate((DAY_ONE, DAY_TWO), start=1)
    )
    snapshot = WeeklyPlanningInputSnapshot(
        snapshot_id="snapshot-one",
        organization_id=ORGANIZATION_ID,
        period_start=DAY_ONE,
        period_end=PERIOD_END,
        operational_unit=UNIT,
        demands=demands,
        workforce_candidates=(_candidate(),),
        policy_set_identifier="policy-set",
        policy_set_version="1",
        created_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        fingerprint="fingerprint-one",
    )

    def assignment_id_factory(**values: object) -> str:
        return f"assignment:{values['operational_date'].isoformat()}"

    generated = generate_weekly_proposal_baseline(
        snapshot=snapshot,
        capability_mappings=(
            WorkloadCapabilityMapping(
                workload_identifier=CAPABILITY,
                required_capabilities=(CAPABILITY,),
            ),
        ),
        existing_assignment_stability_priority=0,
        lower_weekly_load_priority=1,
        continuity_priority=2,
        assignment_id_factory=assignment_id_factory,
    )
    return compose_weekly_workforce_proposal(
        snapshot=snapshot,
        generation_result=generated,
        proposal_id="proposal-one",
        version=1,
        created_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
    )


def _violation() -> ConstraintEvaluation:
    return ConstraintEvaluation(
        code="weekly-hours-capacity",
        category=ConstraintEvaluationCategory.HARD_CONSTRAINT,
        passed=False,
        message="Weekly hours are insufficient.",
        rule_origin="core-policy",
    )


def _override(
    operation: DispatcherOverrideOperationType,
    *,
    assignment_id: str | None = None,
    **updates: object,
) -> DispatcherManualOverride:
    values: dict[str, object] = {
        "override_id": f"override-{operation.value.lower()}",
        "organization_id": ORGANIZATION_ID,
        "proposal_id": "proposal-one",
        "proposal_version": 1,
        "assignment_id": assignment_id,
        "operation_type": operation,
        "reason": "Dispatcher operational correction.",
        "actor_id": "dispatcher-one",
        "violations": (),
        "created_at": CREATED_AT,
    }
    values.update(updates)
    return DispatcherManualOverride(**values)


def _manual_assignment(base, **updates: object):
    values = {
        "origin": ProposedShiftAssignmentOrigin.MANUAL,
        "status": ProposedShiftAssignmentStatus.PROPOSED,
    }
    values.update(updates)
    return base.model_copy(update=values)


def _apply(previous, override, replacement=None):
    command = DispatcherWeeklyEditCommand(
        override=override,
        replacement_assignment=replacement,
        created_at=CREATED_AT,
    )
    return apply_dispatcher_weekly_edit(previous=previous, command=command)


def _gap_by_trace(aggregate):
    return {gap.demand_trace_id: gap for gap in aggregate.coverage_gaps}


def test_add_manual_assignment_creates_revision_and_allows_violations() -> None:
    previous = _previous()
    first = previous.assignments[0]
    replacement = _manual_assignment(
        first,
        assignment_id="assignment-added",
        workforce_member_id="member-manual",
    )
    override = _override(
        DispatcherOverrideOperationType.ADD_ASSIGNMENT,
        violations=(_violation(),),
    )
    before = previous.model_dump(mode="json")

    result = _apply(previous, override, replacement)

    assert len(result.assignments) == 3
    assert replacement in result.assignments
    assert replacement.origin is ProposedShiftAssignmentOrigin.MANUAL
    assert result.proposal.version == 2
    assert previous.model_dump(mode="json") == before
    gap = _gap_by_trace(result)[replacement.demand_trace_id]
    assert gap.proposed_quantity == 2
    assert gap.gap_quantity == -1


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("organization_id", "organization-two"),
        ("date", date(2026, 8, 31)),
        (
            "operational_unit",
            OperationalUnit(external_identifier="unit-two"),
        ),
    ),
)
def test_add_rejects_replacement_outside_structural_scope(
    field: str,
    value: object,
) -> None:
    previous = _previous()
    replacement = _manual_assignment(
        previous.assignments[0],
        assignment_id="assignment-added",
        **{field: value},
    )
    with pytest.raises(DispatcherWeeklyEditScopeMismatchError):
        _apply(
            previous,
            _override(DispatcherOverrideOperationType.ADD_ASSIGNMENT),
            replacement,
        )


def test_remove_existing_assignment_updates_gap_without_mutating_previous() -> None:
    previous = _previous()
    target = previous.assignments[0]
    before = previous.model_dump(mode="json")
    result = _apply(
        previous,
        _override(
            DispatcherOverrideOperationType.REMOVE_ASSIGNMENT,
            assignment_id=target.assignment_id,
        ),
    )

    assert target not in result.assignments
    assert previous.model_dump(mode="json") == before
    gap = _gap_by_trace(result)[target.demand_trace_id]
    assert gap.proposed_quantity == 0
    assert gap.gap_quantity == 1


@pytest.mark.parametrize(
    "operation",
    (
        DispatcherOverrideOperationType.REMOVE_ASSIGNMENT,
        DispatcherOverrideOperationType.REPLACE_ASSIGNMENT,
        DispatcherOverrideOperationType.MOVE_ASSIGNMENT,
        DispatcherOverrideOperationType.MODIFY_ASSIGNMENT,
    ),
)
def test_target_operation_rejects_missing_assignment(
    operation: DispatcherOverrideOperationType,
) -> None:
    previous = _previous()
    replacement = (
        None
        if operation is DispatcherOverrideOperationType.REMOVE_ASSIGNMENT
        else _manual_assignment(previous.assignments[0])
    )
    with pytest.raises(DispatcherWeeklyEditAssignmentNotFoundError):
        _apply(
            previous,
            _override(operation, assignment_id="missing-assignment"),
            replacement,
        )


def test_replace_can_change_driver_assignment_identity_date_and_trace() -> None:
    previous = _previous()
    target = previous.assignments[0]
    other = previous.assignments[1]
    replacement = _manual_assignment(
        target,
        assignment_id="replacement-assignment",
        workforce_member_id="replacement-driver",
        date=other.date,
        time_window=other.time_window,
        demand_trace_id=other.demand_trace_id,
        shift_identifier="manual-shift",
    )
    result = _apply(
        previous,
        _override(
            DispatcherOverrideOperationType.REPLACE_ASSIGNMENT,
            assignment_id=target.assignment_id,
        ),
        replacement,
    )
    assert target not in result.assignments
    assert replacement in result.assignments


def test_move_changes_day_and_trace_but_preserves_identity_and_driver() -> None:
    previous = _previous()
    target, destination = previous.assignments
    replacement = _manual_assignment(
        target,
        date=destination.date,
        time_window=destination.time_window,
        demand_trace_id=destination.demand_trace_id,
    )
    result = _apply(
        previous,
        _override(
            DispatcherOverrideOperationType.MOVE_ASSIGNMENT,
            assignment_id=target.assignment_id,
        ),
        replacement,
    )
    moved = next(
        item for item in result.assignments if item.assignment_id == target.assignment_id
    )
    assert moved.date == DAY_TWO
    assert moved.workforce_member_id == target.workforce_member_id
    assert moved.assignment_id == target.assignment_id


@pytest.mark.parametrize(
    ("field", "value"),
    (("assignment_id", "other-id"), ("workforce_member_id", "other-driver")),
)
def test_move_rejects_identity_or_driver_change(field: str, value: str) -> None:
    previous = _previous()
    target = previous.assignments[0]
    replacement = _manual_assignment(target, **{field: value})
    with pytest.raises(DispatcherWeeklyEditCommandMismatchError):
        _apply(
            previous,
            _override(
                DispatcherOverrideOperationType.MOVE_ASSIGNMENT,
                assignment_id=target.assignment_id,
            ),
            replacement,
        )


def test_modify_keeps_identity_driver_date_and_changes_details() -> None:
    previous = _previous()
    target = previous.assignments[0]
    replacement = _manual_assignment(
        target,
        time_window=TimeWindow(
            external_identifier="window-modified",
            starts_at="09:00",
            ends_at="13:00",
        ),
        shift_identifier="manual-shift",
        capability_or_workload="manual-capability",
    )
    result = _apply(
        previous,
        _override(
            DispatcherOverrideOperationType.MODIFY_ASSIGNMENT,
            assignment_id=target.assignment_id,
        ),
        replacement,
    )
    modified = next(
        item for item in result.assignments if item.assignment_id == target.assignment_id
    )
    assert modified.workforce_member_id == target.workforce_member_id
    assert modified.date == target.date
    assert modified.time_window == replacement.time_window
    assert modified.shift_identifier == "manual-shift"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("assignment_id", "other-id"),
        ("workforce_member_id", "other-driver"),
        ("date", DAY_TWO),
    ),
)
def test_modify_rejects_identity_driver_or_date_change(
    field: str,
    value: object,
) -> None:
    previous = _previous()
    target = previous.assignments[0]
    replacement = _manual_assignment(target, **{field: value})
    with pytest.raises(DispatcherWeeklyEditCommandMismatchError):
        _apply(
            previous,
            _override(
                DispatcherOverrideOperationType.MODIFY_ASSIGNMENT,
                assignment_id=target.assignment_id,
            ),
            replacement,
        )


@pytest.mark.parametrize(
    ("field", "value", "error_type"),
    (
        ("organization_id", "organization-two", DispatcherWeeklyEditScopeMismatchError),
        ("proposal_id", "proposal-two", DispatcherWeeklyEditScopeMismatchError),
        ("proposal_version", 2, DispatcherWeeklyEditCommandMismatchError),
    ),
)
def test_override_scope_and_version_mismatch_are_rejected(
    field: str,
    value: object,
    error_type: type[Exception],
) -> None:
    previous = _previous()
    target = previous.assignments[0]
    override = _override(
        DispatcherOverrideOperationType.REMOVE_ASSIGNMENT,
        assignment_id=target.assignment_id,
    ).model_copy(update={field: value})
    with pytest.raises(error_type):
        _apply(previous, override)


def test_unknown_demand_trace_is_rejected() -> None:
    previous = _previous()
    replacement = _manual_assignment(
        previous.assignments[0],
        assignment_id="assignment-added",
        demand_trace_id="unknown-demand-trace",
    )
    with pytest.raises(DispatcherWeeklyEditUnknownDemandTraceError):
        _apply(
            previous,
            _override(DispatcherOverrideOperationType.ADD_ASSIGNMENT),
            replacement,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("origin", ProposedShiftAssignmentOrigin.AUTOMATIC),
        ("status", ProposedShiftAssignmentStatus.ACCEPTED),
    ),
)
def test_replacement_must_be_manual_and_proposed(field: str, value: object) -> None:
    previous = _previous()
    replacement = _manual_assignment(
        previous.assignments[0],
        assignment_id="assignment-added",
        **{field: value},
    )
    with pytest.raises(DispatcherWeeklyEditCommandMismatchError):
        _apply(
            previous,
            _override(DispatcherOverrideOperationType.ADD_ASSIGNMENT),
            replacement,
        )


def test_command_shape_mismatch_is_rejected() -> None:
    previous = _previous()
    target = previous.assignments[0]
    with pytest.raises(DispatcherWeeklyEditCommandMismatchError):
        _apply(
            previous,
            _override(DispatcherOverrideOperationType.ADD_ASSIGNMENT),
            None,
        )
    with pytest.raises(DispatcherWeeklyEditCommandMismatchError):
        _apply(
            previous,
            _override(
                DispatcherOverrideOperationType.REMOVE_ASSIGNMENT,
                assignment_id=target.assignment_id,
            ),
            _manual_assignment(target),
        )


def test_header_explainability_snapshot_and_policy_are_preserved() -> None:
    previous = _previous()
    target = previous.assignments[0]
    result = _apply(
        previous,
        _override(
            DispatcherOverrideOperationType.REMOVE_ASSIGNMENT,
            assignment_id=target.assignment_id,
        ),
    )

    assert result.proposal.proposal_id == previous.proposal.proposal_id
    assert result.proposal.version == previous.proposal.version + 1
    assert result.proposal.input_snapshot_id == previous.proposal.input_snapshot_id
    assert result.proposal.input_fingerprint == previous.proposal.input_fingerprint
    assert result.proposal.policy_set_identifier == previous.proposal.policy_set_identifier
    assert result.proposal.policy_set_version == previous.proposal.policy_set_version
    assert result.proposal.status is WeeklyWorkforceProposalStatus.GENERATED
    assert result.proposal.created_at == CREATED_AT
    assert result.eligibility_decisions == previous.eligibility_decisions
    assert result.preference_sets == previous.preference_sets
    assert result.ranked_candidates == previous.ranked_candidates


def test_assignments_and_gaps_have_deterministic_order() -> None:
    previous = _previous()
    replacement = _manual_assignment(
        previous.assignments[0],
        assignment_id="aaa-added",
        workforce_member_id="aaa-member",
    )
    result = _apply(
        previous,
        _override(DispatcherOverrideOperationType.ADD_ASSIGNMENT),
        replacement,
    )
    assignment_keys = tuple(
        (
            item.date,
            item.time_window.external_identifier,
            item.workforce_member_id,
            item.assignment_id,
        )
        for item in result.assignments
    )
    assert assignment_keys == tuple(sorted(assignment_keys))
    traces = tuple(gap.demand_trace_id for gap in result.coverage_gaps)
    assert traces == tuple(sorted(traces))


def test_command_override_replacement_and_previous_are_immutable() -> None:
    previous = _previous()
    replacement = _manual_assignment(
        previous.assignments[0], assignment_id="assignment-added"
    )
    override = _override(DispatcherOverrideOperationType.ADD_ASSIGNMENT)
    command = DispatcherWeeklyEditCommand(
        override=override,
        replacement_assignment=replacement,
        created_at=CREATED_AT,
    )
    before = (
        previous.model_dump(mode="json"),
        command.model_dump(mode="json"),
        override.model_dump(mode="json"),
        replacement.model_dump(mode="json"),
    )
    apply_dispatcher_weekly_edit(previous=previous, command=command)
    assert before == (
        previous.model_dump(mode="json"),
        command.model_dump(mode="json"),
        override.model_dump(mode="json"),
        replacement.model_dump(mode="json"),
    )
    with pytest.raises(ValidationError):
        command.created_at = datetime.now(timezone.utc)


def test_domain_edit_has_no_generator_persistence_clock_or_runtime_wiring() -> None:
    source = getsource(dispatcher_weekly_edit).casefold()
    forbidden = (
        "generate_weekly_proposal_baseline",
        "evaluate_workforce_candidate_eligibility",
        "db_session",
        "repository",
        "datetime.now",
        "utcnow",
        "uuid",
        "random",
        "fastapi",
        "approve",
        "publish",
        "lock",
    )
    assert all(term not in source for term in forbidden)
