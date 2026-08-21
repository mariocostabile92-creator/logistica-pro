from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.workforce_auto_planning.proposed_shift_assignment import (
    ProposedShiftAssignment,
)
from app.domain.workforce_auto_planning.weekly_proposal_composer import (
    ComposedWeeklyWorkforceProposal,
)
from app.domain.workforce_auto_planning.weekly_workforce_proposal import (
    WeeklyWorkforceProposal,
    WeeklyWorkforceProposalStatus,
)


class DispatcherAssignmentLockError(ValueError):
    pass


class DispatcherAssignmentLockAssignmentNotFoundError(
    DispatcherAssignmentLockError
):
    pass


class DispatcherAssignmentLockScopeMismatchError(DispatcherAssignmentLockError):
    pass


class DispatcherAssignmentLockCommand(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    organization_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    proposal_version: int = Field(gt=0, strict=True)
    assignment_id: str = Field(min_length=1)
    locked: bool = Field(strict=True)
    actor_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    created_at: datetime


def _validate_scope(
    *,
    previous: ComposedWeeklyWorkforceProposal,
    command: DispatcherAssignmentLockCommand,
) -> None:
    proposal = previous.proposal
    if (
        command.organization_id != proposal.organization_id
        or command.proposal_id != proposal.proposal_id
        or command.proposal_version != proposal.version
    ):
        raise DispatcherAssignmentLockScopeMismatchError(
            "assignment lock command does not match proposal scope"
        )


def _resolve_assignment(
    *,
    previous: ComposedWeeklyWorkforceProposal,
    assignment_id: str,
) -> ProposedShiftAssignment:
    matches = tuple(
        assignment
        for assignment in previous.assignments
        if assignment.assignment_id == assignment_id
    )
    if len(matches) != 1:
        raise DispatcherAssignmentLockAssignmentNotFoundError(
            "assignment_id must resolve to exactly one proposal assignment"
        )
    return matches[0]


def _with_lock_state(
    *,
    assignment: ProposedShiftAssignment,
    locked: bool,
) -> ProposedShiftAssignment:
    return ProposedShiftAssignment.model_validate(
        {
            **assignment.model_dump(),
            "locked": locked,
        }
    )


def apply_dispatcher_assignment_lock(
    *,
    previous: ComposedWeeklyWorkforceProposal,
    command: DispatcherAssignmentLockCommand,
) -> ComposedWeeklyWorkforceProposal:
    _validate_scope(previous=previous, command=command)
    target = _resolve_assignment(
        previous=previous,
        assignment_id=command.assignment_id,
    )
    updated_target = _with_lock_state(
        assignment=target,
        locked=command.locked,
    )
    assignments = tuple(
        updated_target if assignment is target else assignment
        for assignment in previous.assignments
    )
    proposal = previous.proposal
    next_proposal = WeeklyWorkforceProposal(
        proposal_id=proposal.proposal_id,
        organization_id=proposal.organization_id,
        period_start=proposal.period_start,
        period_end=proposal.period_end,
        operational_unit=proposal.operational_unit,
        version=proposal.version + 1,
        input_snapshot_id=proposal.input_snapshot_id,
        input_fingerprint=proposal.input_fingerprint,
        policy_set_identifier=proposal.policy_set_identifier,
        policy_set_version=proposal.policy_set_version,
        status=WeeklyWorkforceProposalStatus.GENERATED,
        created_at=command.created_at,
    )
    return ComposedWeeklyWorkforceProposal(
        proposal=next_proposal,
        assignments=assignments,
        coverage_gaps=previous.coverage_gaps,
        eligibility_decisions=previous.eligibility_decisions,
        preference_sets=previous.preference_sets,
        ranked_candidates=previous.ranked_candidates,
    )
