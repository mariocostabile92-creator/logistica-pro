from datetime import datetime, timezone
from inspect import getsource

import pytest
from pydantic import ValidationError

from app.domain.workforce_auto_planning import (
    CoverageGap,
    ProposedShiftAssignmentOrigin,
    WeeklyProposalStatusTransitionCommand,
    WeeklyProposalStatusTransitionNotAllowedError,
    WeeklyProposalStatusTransitionScopeMismatchError,
    WeeklyWorkforceProposalStatus,
    apply_weekly_proposal_status_transition,
)
from app.domain.workforce_auto_planning import (
    weekly_proposal_status_transition as transition_module,
)
from tests.test_weekly_proposal_dispatcher_edit_service import (
    _scenario,
)


TRANSITION_AT = datetime(2026, 8, 25, 9, tzinfo=timezone.utc)


def _command(
    previous,
    target_status: WeeklyWorkforceProposalStatus,
    **updates: object,
) -> WeeklyProposalStatusTransitionCommand:
    values: dict[str, object] = {
        "organization_id": previous.proposal.organization_id,
        "proposal_id": previous.proposal.proposal_id,
        "proposal_version": previous.proposal.version,
        "target_status": target_status,
        "actor_id": "dispatcher-one",
        "reason": "Dispatcher review completed.",
        "created_at": TRANSITION_AT,
    }
    values.update(updates)
    return WeeklyProposalStatusTransitionCommand(**values)


def _under_review(previous):
    return apply_weekly_proposal_status_transition(
        previous=previous,
        command=_command(
            previous,
            WeeklyWorkforceProposalStatus.UNDER_REVIEW,
        ),
    )


def test_generated_can_transition_to_under_review_as_a_new_revision() -> None:
    _, previous = _scenario()

    result = _under_review(previous)

    assert result.proposal.status == WeeklyWorkforceProposalStatus.UNDER_REVIEW
    assert result.proposal.version == previous.proposal.version + 1
    assert result.proposal.proposal_id == previous.proposal.proposal_id
    assert result.proposal.created_at == TRANSITION_AT


def test_under_review_can_transition_to_approved_as_a_new_revision() -> None:
    _, generated = _scenario()
    previous = _under_review(generated)
    approved_at = datetime(2026, 8, 25, 11, tzinfo=timezone.utc)

    result = apply_weekly_proposal_status_transition(
        previous=previous,
        command=_command(
            previous,
            WeeklyWorkforceProposalStatus.APPROVED,
            created_at=approved_at,
        ),
    )

    assert result.proposal.status == WeeklyWorkforceProposalStatus.APPROVED
    assert result.proposal.version == previous.proposal.version + 1
    assert result.proposal.created_at == approved_at


@pytest.mark.parametrize(
    ("source", "target"),
    (
        (WeeklyWorkforceProposalStatus.DRAFT, WeeklyWorkforceProposalStatus.GENERATED),
        (WeeklyWorkforceProposalStatus.GENERATED, WeeklyWorkforceProposalStatus.APPROVED),
        (WeeklyWorkforceProposalStatus.GENERATED, WeeklyWorkforceProposalStatus.SUPERSEDED),
        (WeeklyWorkforceProposalStatus.UNDER_REVIEW, WeeklyWorkforceProposalStatus.GENERATED),
        (WeeklyWorkforceProposalStatus.UNDER_REVIEW, WeeklyWorkforceProposalStatus.SUPERSEDED),
        (WeeklyWorkforceProposalStatus.APPROVED, WeeklyWorkforceProposalStatus.GENERATED),
        (WeeklyWorkforceProposalStatus.APPROVED, WeeklyWorkforceProposalStatus.UNDER_REVIEW),
        (WeeklyWorkforceProposalStatus.SUPERSEDED, WeeklyWorkforceProposalStatus.UNDER_REVIEW),
        (WeeklyWorkforceProposalStatus.SUPERSEDED, WeeklyWorkforceProposalStatus.APPROVED),
    ),
)
def test_every_other_cross_status_transition_is_rejected(
    source: WeeklyWorkforceProposalStatus,
    target: WeeklyWorkforceProposalStatus,
) -> None:
    _, generated = _scenario()
    previous = generated.model_copy(
        update={"proposal": generated.proposal.model_copy(update={"status": source})}
    )

    with pytest.raises(
        WeeklyProposalStatusTransitionNotAllowedError,
        match=f"{source.value} -> {target.value}",
    ):
        apply_weekly_proposal_status_transition(
            previous=previous,
            command=_command(previous, target),
        )


@pytest.mark.parametrize("status", tuple(WeeklyWorkforceProposalStatus))
def test_same_status_transition_is_rejected(
    status: WeeklyWorkforceProposalStatus,
) -> None:
    _, generated = _scenario()
    previous = generated.model_copy(
        update={"proposal": generated.proposal.model_copy(update={"status": status})}
    )

    with pytest.raises(WeeklyProposalStatusTransitionNotAllowedError):
        apply_weekly_proposal_status_transition(
            previous=previous,
            command=_command(previous, status),
        )


@pytest.mark.parametrize(
    "updates",
    (
        {"organization_id": "another-organization"},
        {"proposal_id": "another-proposal"},
        {"proposal_version": 99},
    ),
)
def test_command_scope_mismatch_is_rejected(updates: dict[str, object]) -> None:
    _, previous = _scenario()

    with pytest.raises(WeeklyProposalStatusTransitionScopeMismatchError):
        apply_weekly_proposal_status_transition(
            previous=previous,
            command=_command(
                previous,
                WeeklyWorkforceProposalStatus.UNDER_REVIEW,
                **updates,
            ),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("organization_id", " "),
        ("proposal_id", " "),
        ("proposal_version", 0),
        ("proposal_version", True),
        ("actor_id", " "),
        ("reason", " "),
    ),
)
def test_command_rejects_invalid_required_values(field: str, value: object) -> None:
    _, previous = _scenario()

    with pytest.raises(ValidationError):
        _command(
            previous,
            WeeklyWorkforceProposalStatus.UNDER_REVIEW,
            **{field: value},
        )


def test_transition_preserves_snapshot_policy_scope_and_all_aggregate_content() -> None:
    _, previous = _scenario()

    result = _under_review(previous)

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
    assert result.assignments is previous.assignments
    assert result.coverage_gaps is previous.coverage_gaps
    assert result.eligibility_decisions is previous.eligibility_decisions
    assert result.preference_sets is previous.preference_sets
    assert result.ranked_candidates is previous.ranked_candidates
    assert tuple(item.locked for item in result.assignments) == tuple(
        item.locked for item in previous.assignments
    )


def test_approval_does_not_apply_readiness_gap_or_violation_gates() -> None:
    _, generated = _scenario()
    previous = _under_review(generated)
    existing_gap = previous.coverage_gaps[0]
    positive_gap = CoverageGap.model_validate(
        {
            **existing_gap.model_dump(),
            "required_quantity": 2,
            "proposed_quantity": 1,
            "gap_quantity": 1,
        }
    )
    manual_locked_assignment = previous.assignments[0].model_copy(
        update={
            "origin": ProposedShiftAssignmentOrigin.MANUAL,
            "locked": True,
        }
    )
    previous_with_unresolved_evidence = previous.model_copy(
        update={
            "assignments": (
                manual_locked_assignment,
                *previous.assignments[1:],
            ),
            "coverage_gaps": (positive_gap, *previous.coverage_gaps[1:]),
        }
    )
    assert any(
        not evaluation.passed
        for decision in previous_with_unresolved_evidence.eligibility_decisions
        for evaluation in decision.evaluations
    )

    result = apply_weekly_proposal_status_transition(
        previous=previous_with_unresolved_evidence,
        command=_command(
            previous_with_unresolved_evidence,
            WeeklyWorkforceProposalStatus.APPROVED,
        ),
    )

    assert result.proposal.status == WeeklyWorkforceProposalStatus.APPROVED
    assert result.assignments[0].origin is ProposedShiftAssignmentOrigin.MANUAL
    assert result.assignments[0].locked is True
    assert result.coverage_gaps[0].gap_quantity == 1
    assert result.eligibility_decisions is previous.eligibility_decisions


def test_transition_does_not_mutate_previous_or_command() -> None:
    _, previous = _scenario()
    command = _command(previous, WeeklyWorkforceProposalStatus.UNDER_REVIEW)
    previous_before = previous.model_dump(mode="json")
    command_before = command.model_dump(mode="json")

    result = apply_weekly_proposal_status_transition(
        previous=previous,
        command=command,
    )

    assert previous.model_dump(mode="json") == previous_before
    assert command.model_dump(mode="json") == command_before
    assert result is not previous
    with pytest.raises(ValidationError):
        result.proposal.status = WeeklyWorkforceProposalStatus.APPROVED
    with pytest.raises(ValidationError):
        command.reason = "changed"


def test_transition_contract_remains_pure_core_logic() -> None:
    source = getsource(transition_module).lower()

    for forbidden in (
        "repository",
        "sqlalchemy",
        "fastapi",
        "db_session",
        "publish",
        "event_repository",
        "generator",
        "readiness",
    ):
        assert forbidden not in source
