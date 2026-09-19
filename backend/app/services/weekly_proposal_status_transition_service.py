from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    WeeklyPlanningInputSnapshot,
)
from app.domain.workforce_auto_planning.weekly_proposal_composer import (
    ComposedWeeklyWorkforceProposal,
)
from app.domain.workforce_auto_planning.weekly_proposal_event import (
    WeeklyWorkforceProposalEvent,
)
from app.domain.workforce_auto_planning.weekly_proposal_repository import (
    WeeklyWorkforceProposalRepository,
)
from app.domain.workforce_auto_planning.weekly_proposal_status_transition import (
    WeeklyProposalStatusTransitionCommand,
    apply_weekly_proposal_status_transition,
)
from app.domain.workforce_auto_planning.weekly_workforce_proposal import (
    WeeklyWorkforceProposalStatus,
)
from app.repositories.weekly_workforce_proposal_unit_of_work import (
    WeeklyWorkforceProposalUnitOfWork,
)
from app.services.weekly_proposal_regeneration_service import (
    WeeklyProposalRegenerationStaleRevisionError,
)


WEEKLY_PROPOSAL_UNDER_REVIEW_EVENT_TYPE = "WEEKLY_PROPOSAL_UNDER_REVIEW"
WEEKLY_PROPOSAL_APPROVED_EVENT_TYPE = "WEEKLY_PROPOSAL_APPROVED"
WeeklyProposalStatusTransitionEventIdFactory = Callable[..., str]


class WeeklyProposalStatusTransitionEventPayload(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    previous_status: WeeklyWorkforceProposalStatus
    target_status: WeeklyWorkforceProposalStatus
    previous_version: StrictInt = Field(gt=0)
    new_version: StrictInt = Field(gt=0)
    actor_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    input_snapshot_id: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)


_EVENT_TYPE_BY_TARGET = {
    WeeklyWorkforceProposalStatus.UNDER_REVIEW: (
        WEEKLY_PROPOSAL_UNDER_REVIEW_EVENT_TYPE
    ),
    WeeklyWorkforceProposalStatus.APPROVED: WEEKLY_PROPOSAL_APPROVED_EVENT_TYPE,
}


def persist_weekly_proposal_status_transition(
    *,
    organization_id: str,
    proposal_id: str,
    previous_version: int,
    snapshot: WeeklyPlanningInputSnapshot,
    command: WeeklyProposalStatusTransitionCommand,
    event_id_factory: WeeklyProposalStatusTransitionEventIdFactory,
    repository: WeeklyWorkforceProposalRepository,
    unit_of_work: WeeklyWorkforceProposalUnitOfWork,
) -> ComposedWeeklyWorkforceProposal:
    previous = repository.get_revision(
        organization_id=organization_id,
        proposal_id=proposal_id,
        version=previous_version,
    )
    latest = repository.latest_revision(
        organization_id=organization_id,
        proposal_id=proposal_id,
    )
    if latest.proposal.version != previous_version:
        raise WeeklyProposalRegenerationStaleRevisionError(
            "previous proposal revision is stale"
        )

    transitioned = apply_weekly_proposal_status_transition(
        previous=previous,
        command=command,
    )
    event_type = _EVENT_TYPE_BY_TARGET[command.target_status]
    event_id = event_id_factory(
        organization_id=organization_id,
        proposal_id=proposal_id,
        proposal_version=transitioned.proposal.version,
        event_type=event_type,
        previous_status=previous.proposal.status,
        target_status=transitioned.proposal.status,
    )
    event = WeeklyWorkforceProposalEvent(
        event_id=event_id,
        organization_id=organization_id,
        proposal_id=proposal_id,
        proposal_version=transitioned.proposal.version,
        event_type=event_type,
        actor_id=command.actor_id,
        reason=command.reason,
        payload=WeeklyProposalStatusTransitionEventPayload(
            previous_status=previous.proposal.status,
            target_status=transitioned.proposal.status,
            previous_version=previous.proposal.version,
            new_version=transitioned.proposal.version,
            actor_id=command.actor_id,
            reason=command.reason,
            input_snapshot_id=transitioned.proposal.input_snapshot_id,
            input_fingerprint=transitioned.proposal.input_fingerprint,
        ),
        created_at=command.created_at,
    )

    with unit_of_work.transaction() as transaction:
        persisted = transaction.proposals.save_revision(
            organization_id=organization_id,
            snapshot=snapshot,
            aggregate=transitioned,
        )
        transaction.events.append_event(
            organization_id=organization_id,
            event=event,
        )
    return persisted
