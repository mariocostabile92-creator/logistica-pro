from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.domain.workforce_auto_planning.constraint_evaluation import (
    ConstraintEvaluation,
)
from app.domain.workforce_auto_planning.dispatcher_manual_override import (
    DispatcherOverrideOperationType,
)
from app.domain.workforce_auto_planning.dispatcher_manual_override_revalidation import (
    revalidate_dispatcher_manual_override,
)
from app.domain.workforce_auto_planning.dispatcher_weekly_edit import (
    DispatcherWeeklyEditCommand,
    apply_dispatcher_weekly_edit,
)
from app.domain.workforce_auto_planning.planning_policy import (
    WorkloadCapabilityMapping,
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


DISPATCHER_MANUAL_EDIT_EVENT_TYPE = "DISPATCHER_MANUAL_EDIT"
WeeklyProposalEventIdFactory = Callable[..., str]


class DispatcherManualEditEventPayload(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    override_id: str = Field(min_length=1)
    operation_type: DispatcherOverrideOperationType
    target_assignment_id: str | None = Field(default=None, min_length=1)
    replacement_assignment_id: str | None = Field(default=None, min_length=1)
    previous_version: StrictInt = Field(gt=0)
    new_version: StrictInt = Field(gt=0)
    violations: tuple[ConstraintEvaluation, ...] = Field(default_factory=tuple)


def persist_dispatcher_weekly_edit(
    *,
    organization_id: str,
    proposal_id: str,
    previous_version: int,
    snapshot: WeeklyPlanningInputSnapshot,
    command: DispatcherWeeklyEditCommand,
    capability_mappings: tuple[WorkloadCapabilityMapping, ...],
    event_id_factory: WeeklyProposalEventIdFactory,
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

    revalidated_override = revalidate_dispatcher_manual_override(
        snapshot=snapshot,
        previous=previous,
        override=command.override,
        replacement_assignment=command.replacement_assignment,
        capability_mappings=capability_mappings,
    )
    revalidated_command = DispatcherWeeklyEditCommand(
        override=revalidated_override,
        replacement_assignment=command.replacement_assignment,
        created_at=command.created_at,
    )
    edited_revision = apply_dispatcher_weekly_edit(
        previous=previous,
        command=revalidated_command,
    )

    event_id = event_id_factory(
        organization_id=organization_id,
        proposal_id=proposal_id,
        proposal_version=edited_revision.proposal.version,
        override_id=revalidated_override.override_id,
        event_type=DISPATCHER_MANUAL_EDIT_EVENT_TYPE,
    )
    event = WeeklyWorkforceProposalEvent(
        event_id=event_id,
        organization_id=organization_id,
        proposal_id=proposal_id,
        proposal_version=edited_revision.proposal.version,
        event_type=DISPATCHER_MANUAL_EDIT_EVENT_TYPE,
        actor_id=revalidated_override.actor_id,
        reason=revalidated_override.reason,
        payload=DispatcherManualEditEventPayload(
            override_id=revalidated_override.override_id,
            operation_type=revalidated_override.operation_type,
            target_assignment_id=revalidated_override.assignment_id,
            replacement_assignment_id=(
                command.replacement_assignment.assignment_id
                if command.replacement_assignment is not None
                else None
            ),
            previous_version=previous.proposal.version,
            new_version=edited_revision.proposal.version,
            violations=revalidated_override.violations,
        ),
        created_at=revalidated_override.created_at,
    )

    with unit_of_work.transaction() as transaction:
        persisted = transaction.proposals.save_revision(
            organization_id=organization_id,
            snapshot=snapshot,
            aggregate=edited_revision,
        )
        transaction.events.append_event(
            organization_id=organization_id,
            event=event,
        )
    return persisted
