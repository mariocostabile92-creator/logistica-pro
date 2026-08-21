from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from app.domain.workforce_auto_planning.dispatcher_assignment_lock import (
    DispatcherAssignmentLockCommand,
    apply_dispatcher_assignment_lock,
)
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
from app.repositories.weekly_workforce_proposal_unit_of_work import (
    WeeklyWorkforceProposalUnitOfWork,
)
from app.services.weekly_proposal_regeneration_service import (
    WeeklyProposalRegenerationStaleRevisionError,
)


DISPATCHER_ASSIGNMENT_LOCKED_EVENT_TYPE = "DISPATCHER_ASSIGNMENT_LOCKED"
DISPATCHER_ASSIGNMENT_UNLOCKED_EVENT_TYPE = "DISPATCHER_ASSIGNMENT_UNLOCKED"
WeeklyProposalLockEventIdFactory = Callable[..., str]


class DispatcherAssignmentLockEventPayload(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    assignment_id: str = Field(min_length=1)
    locked: StrictBool
    previous_version: StrictInt = Field(gt=0)
    new_version: StrictInt = Field(gt=0)
    actor_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


def persist_dispatcher_assignment_lock(
    *,
    organization_id: str,
    proposal_id: str,
    previous_version: int,
    snapshot: WeeklyPlanningInputSnapshot,
    command: DispatcherAssignmentLockCommand,
    event_id_factory: WeeklyProposalLockEventIdFactory,
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

    locked_revision = apply_dispatcher_assignment_lock(
        previous=previous,
        command=command,
    )
    event_type = (
        DISPATCHER_ASSIGNMENT_LOCKED_EVENT_TYPE
        if command.locked
        else DISPATCHER_ASSIGNMENT_UNLOCKED_EVENT_TYPE
    )
    event_id = event_id_factory(
        organization_id=organization_id,
        proposal_id=proposal_id,
        proposal_version=locked_revision.proposal.version,
        assignment_id=command.assignment_id,
        event_type=event_type,
    )
    event = WeeklyWorkforceProposalEvent(
        event_id=event_id,
        organization_id=organization_id,
        proposal_id=proposal_id,
        proposal_version=locked_revision.proposal.version,
        event_type=event_type,
        actor_id=command.actor_id,
        reason=command.reason,
        payload=DispatcherAssignmentLockEventPayload(
            assignment_id=command.assignment_id,
            locked=command.locked,
            previous_version=previous.proposal.version,
            new_version=locked_revision.proposal.version,
            actor_id=command.actor_id,
            reason=command.reason,
        ),
        created_at=command.created_at,
    )

    with unit_of_work.transaction() as transaction:
        persisted = transaction.proposals.save_revision(
            organization_id=organization_id,
            snapshot=snapshot,
            aggregate=locked_revision,
        )
        transaction.events.append_event(
            organization_id=organization_id,
            event=event,
        )
    return persisted
