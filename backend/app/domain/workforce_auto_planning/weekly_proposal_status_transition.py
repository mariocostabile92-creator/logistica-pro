from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.domain.workforce_auto_planning.weekly_proposal_composer import (
    ComposedWeeklyWorkforceProposal,
)
from app.domain.workforce_auto_planning.weekly_workforce_proposal import (
    WeeklyWorkforceProposal,
    WeeklyWorkforceProposalStatus,
)


class WeeklyProposalStatusTransitionError(ValueError):
    pass


class WeeklyProposalStatusTransitionScopeMismatchError(
    WeeklyProposalStatusTransitionError
):
    pass


class WeeklyProposalStatusTransitionNotAllowedError(
    WeeklyProposalStatusTransitionError
):
    pass


class WeeklyProposalStatusTransitionCommand(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    organization_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    proposal_version: StrictInt = Field(gt=0)
    target_status: WeeklyWorkforceProposalStatus
    actor_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    created_at: datetime


_ALLOWED_TRANSITIONS = frozenset(
    {
        (
            WeeklyWorkforceProposalStatus.GENERATED,
            WeeklyWorkforceProposalStatus.UNDER_REVIEW,
        ),
        (
            WeeklyWorkforceProposalStatus.UNDER_REVIEW,
            WeeklyWorkforceProposalStatus.APPROVED,
        ),
    }
)


def apply_weekly_proposal_status_transition(
    *,
    previous: ComposedWeeklyWorkforceProposal,
    command: WeeklyProposalStatusTransitionCommand,
) -> ComposedWeeklyWorkforceProposal:
    proposal = previous.proposal
    if (
        command.organization_id != proposal.organization_id
        or command.proposal_id != proposal.proposal_id
        or command.proposal_version != proposal.version
    ):
        raise WeeklyProposalStatusTransitionScopeMismatchError(
            "proposal status transition command does not match proposal scope"
        )

    transition = (proposal.status, command.target_status)
    if transition not in _ALLOWED_TRANSITIONS:
        raise WeeklyProposalStatusTransitionNotAllowedError(
            f"proposal status transition is not allowed: "
            f"{proposal.status.value} -> {command.target_status.value}"
        )

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
        status=command.target_status,
        created_at=command.created_at,
    )
    return previous.model_copy(update={"proposal": next_proposal})
