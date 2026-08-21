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
    DispatcherAssignmentLockAssignmentNotFoundError,
    DispatcherAssignmentLockCommand,
    DispatcherAssignmentLockScopeMismatchError,
    OperationalDemand,
    ProposedShiftAssignmentOrigin,
    ProposedShiftAssignmentStatus,
    WeeklyPlanningInputSnapshot,
    WeeklyWorkforceProposalStatus,
    WorkforceCandidateAvailabilitySnapshot,
    WorkforceCandidateSnapshot,
    WorkloadCapabilityMapping,
    apply_dispatcher_assignment_lock,
    compose_weekly_workforce_proposal,
    generate_weekly_proposal_baseline,
)
from app.domain.workforce_auto_planning import dispatcher_assignment_lock


ORGANIZATION_ID = "organization-one"
UNIT = OperationalUnit(external_identifier="unit-one", name="Unit one")
DAY_ONE = date(2026, 8, 24)
DAY_TWO = date(2026, 8, 25)
PERIOD_END = date(2026, 8, 30)
CREATED_AT = datetime(2026, 8, 23, 10, tzinfo=timezone.utc)
LOCKED_AT = datetime(2026, 8, 24, 9, tzinfo=timezone.utc)
CAPABILITY = "opaque-capability"


def _window(index: int) -> TimeWindow:
    return TimeWindow(
        external_identifier=f"window-{index}",
        starts_at="08:00",
        ends_at="12:00",
    )


def _candidate() -> WorkforceCandidateSnapshot:
    return WorkforceCandidateSnapshot(
        organization_id=ORGANIZATION_ID,
        human_resource=HumanResource(
            external_identifier="member-one",
            capabilities=(CAPABILITY,),
        ),
        availability=tuple(
            WorkforceCandidateAvailabilitySnapshot(
                date=operational_date,
                availability=ResourceAvailability(
                    resource_identifier="member-one",
                    resource_kind=ResourceKind.HUMAN_RESOURCE,
                    available=True,
                    observed_state="available",
                ),
            )
            for operational_date in (DAY_ONE, DAY_TWO)
        ),
        applicable_contract_state={"weekly_hours": Decimal("40")},
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


def _previous(*, target_locked: bool = False, target_manual: bool = False):
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
        created_at=CREATED_AT,
        fingerprint="fingerprint-one",
    )
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
        assignment_id_factory=lambda **values: (
            f"assignment:{values['operational_date'].isoformat()}"
        ),
    )
    aggregate = compose_weekly_workforce_proposal(
        snapshot=snapshot,
        generation_result=generated,
        proposal_id="proposal-one",
        version=3,
        created_at=CREATED_AT,
    )
    target = aggregate.assignments[0].model_copy(
        update={
            "locked": target_locked,
            "origin": (
                ProposedShiftAssignmentOrigin.MANUAL
                if target_manual
                else ProposedShiftAssignmentOrigin.AUTOMATIC
            ),
        }
    )
    return aggregate.model_copy(
        update={"assignments": (target, *aggregate.assignments[1:])}
    )


def _command(
    *,
    locked: object = True,
    **updates: object,
) -> DispatcherAssignmentLockCommand:
    values: dict[str, object] = {
        "organization_id": ORGANIZATION_ID,
        "proposal_id": "proposal-one",
        "proposal_version": 3,
        "assignment_id": "assignment:2026-08-24",
        "locked": locked,
        "actor_id": "dispatcher-one",
        "reason": "Preserve dispatcher decision.",
        "created_at": LOCKED_AT,
    }
    values.update(updates)
    return DispatcherAssignmentLockCommand(**values)


def _apply(*, previous=None, locked: bool):
    selected = previous if previous is not None else _previous()
    return apply_dispatcher_assignment_lock(
        previous=selected,
        command=_command(locked=locked),
    )


def _target(aggregate):
    return next(
        item
        for item in aggregate.assignments
        if item.assignment_id == "assignment:2026-08-24"
    )


def test_lock_unlocked_assignment_sets_locked_true() -> None:
    result = _apply(locked=True)

    assert _target(result).locked is True


def test_unlock_locked_assignment_sets_locked_false() -> None:
    result = _apply(previous=_previous(target_locked=True), locked=False)

    assert _target(result).locked is False


@pytest.mark.parametrize(
    ("initial", "requested"),
    ((True, True), (False, False)),
)
def test_same_lock_state_still_creates_new_revision(
    initial: bool,
    requested: bool,
) -> None:
    previous = _previous(target_locked=initial)

    result = _apply(previous=previous, locked=requested)

    assert _target(result).locked is requested
    assert result.proposal.version == previous.proposal.version + 1
    assert result is not previous


@pytest.mark.parametrize("manual", (False, True))
def test_lock_preserves_every_target_field_except_locked(manual: bool) -> None:
    previous = _previous(target_manual=manual)
    original = _target(previous)

    result = _apply(previous=previous, locked=True)
    updated = _target(result)

    assert updated.model_dump(exclude={"locked"}) == original.model_dump(
        exclude={"locked"}
    )
    assert updated.assignment_id == original.assignment_id
    assert updated.demand_trace_id == original.demand_trace_id
    assert updated.workforce_member_id == original.workforce_member_id
    assert updated.date == original.date
    assert updated.operational_unit == original.operational_unit
    assert updated.time_window == original.time_window
    assert updated.shift_identifier == original.shift_identifier
    assert updated.origin == original.origin
    assert updated.status == original.status
    assert updated.reasons == original.reasons
    assert updated.deterministic_priority == original.deterministic_priority


def test_automatic_origin_remains_automatic() -> None:
    result = _apply(previous=_previous(target_manual=False), locked=True)

    assert _target(result).origin is ProposedShiftAssignmentOrigin.AUTOMATIC


def test_manual_origin_remains_manual() -> None:
    result = _apply(previous=_previous(target_manual=True), locked=True)

    assert _target(result).origin is ProposedShiftAssignmentOrigin.MANUAL


def test_assignment_status_is_preserved() -> None:
    previous = _previous()
    original = _target(previous).model_copy(
        update={"status": ProposedShiftAssignmentStatus.ACCEPTED}
    )
    previous = previous.model_copy(
        update={"assignments": (original, *previous.assignments[1:])}
    )

    result = _apply(previous=previous, locked=True)

    assert _target(result).status is ProposedShiftAssignmentStatus.ACCEPTED


def test_non_target_assignments_and_order_are_preserved_exactly() -> None:
    previous = _previous()
    non_target = previous.assignments[1]

    result = _apply(previous=previous, locked=True)

    assert [item.assignment_id for item in result.assignments] == [
        item.assignment_id for item in previous.assignments
    ]
    assert result.assignments[1] is non_target


def test_gaps_and_explainability_are_preserved_exactly() -> None:
    previous = _previous()

    result = _apply(previous=previous, locked=True)

    assert result.coverage_gaps == previous.coverage_gaps
    assert result.eligibility_decisions == previous.eligibility_decisions
    assert result.preference_sets == previous.preference_sets
    assert result.ranked_candidates == previous.ranked_candidates


def test_revision_preserves_scope_and_uses_command_timestamp() -> None:
    previous = _previous()

    result = _apply(previous=previous, locked=True)

    assert result.proposal.proposal_id == previous.proposal.proposal_id
    assert result.proposal.organization_id == previous.proposal.organization_id
    assert result.proposal.period_start == previous.proposal.period_start
    assert result.proposal.period_end == previous.proposal.period_end
    assert result.proposal.operational_unit == previous.proposal.operational_unit
    assert result.proposal.input_snapshot_id == previous.proposal.input_snapshot_id
    assert result.proposal.input_fingerprint == previous.proposal.input_fingerprint
    assert (
        result.proposal.policy_set_identifier
        == previous.proposal.policy_set_identifier
    )
    assert result.proposal.policy_set_version == previous.proposal.policy_set_version
    assert result.proposal.version == previous.proposal.version + 1
    assert result.proposal.status is WeeklyWorkforceProposalStatus.GENERATED
    assert result.proposal.created_at == LOCKED_AT


def test_previous_command_and_original_assignment_are_immutable() -> None:
    previous = _previous()
    command = _command(locked=True)
    original = _target(previous)
    previous_before = previous.model_dump(mode="json")
    command_before = command.model_dump(mode="json")
    original_before = original.model_dump(mode="json")

    result = apply_dispatcher_assignment_lock(
        previous=previous,
        command=command,
    )

    assert previous.model_dump(mode="json") == previous_before
    assert command.model_dump(mode="json") == command_before
    assert original.model_dump(mode="json") == original_before
    assert _target(result) is not original


def test_unknown_assignment_is_rejected() -> None:
    with pytest.raises(DispatcherAssignmentLockAssignmentNotFoundError):
        apply_dispatcher_assignment_lock(
            previous=_previous(),
            command=_command(locked=True, assignment_id="unknown-assignment"),
        )


def test_ambiguous_assignment_identity_is_rejected() -> None:
    previous = _previous()
    target = _target(previous)
    previous = previous.model_copy(
        update={"assignments": (*previous.assignments, target)}
    )

    with pytest.raises(DispatcherAssignmentLockAssignmentNotFoundError):
        _apply(previous=previous, locked=True)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("organization_id", "organization-two"),
        ("proposal_id", "proposal-two"),
        ("proposal_version", 2),
    ),
)
def test_scope_mismatch_is_rejected(field: str, value: object) -> None:
    with pytest.raises(DispatcherAssignmentLockScopeMismatchError):
        apply_dispatcher_assignment_lock(
            previous=_previous(),
            command=_command(locked=True, **{field: value}),
        )


@pytest.mark.parametrize(
    "updates",
    (
        {"organization_id": " "},
        {"proposal_id": " "},
        {"assignment_id": " "},
        {"actor_id": " "},
        {"reason": " "},
        {"proposal_version": 0},
        {"proposal_version": True},
        {"locked": 1},
    ),
)
def test_command_rejects_invalid_values(updates: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _command(**updates)


def test_command_is_immutable() -> None:
    command = _command(locked=True)

    with pytest.raises(ValidationError):
        command.locked = False


def test_lock_does_not_evaluate_or_generate_or_persist() -> None:
    source = getsource(dispatcher_assignment_lock)

    assert "evaluate_workforce_candidate_eligibility" not in source
    assert "generate_weekly_proposal_baseline" not in source
    assert "repository" not in source.casefold()
    assert "sqlalchemy" not in source.casefold()
    assert "fastapi" not in source.casefold()
