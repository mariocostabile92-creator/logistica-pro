from datetime import datetime

from app.domain.workforce_auto_planning.planning_policy import (
    WorkloadCapabilityMapping,
)
from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    WeeklyPlanningInputSnapshot,
)
from app.domain.workforce_auto_planning.weekly_proposal_composer import (
    ComposedWeeklyWorkforceProposal,
)
from app.domain.workforce_auto_planning.weekly_proposal_generator import (
    AssignmentIdFactory,
    generate_weekly_proposal_baseline,
)
from app.domain.workforce_auto_planning.weekly_proposal_repository import (
    WeeklyWorkforceProposalRepository,
)
from app.domain.workforce_auto_planning.weekly_proposal_revision import (
    compose_next_weekly_proposal_revision,
)


class WeeklyProposalRegenerationStaleRevisionError(RuntimeError):
    pass


def regenerate_weekly_workforce_proposal(
    *,
    organization_id: str,
    proposal_id: str,
    previous_version: int,
    snapshot: WeeklyPlanningInputSnapshot,
    capability_mappings: tuple[WorkloadCapabilityMapping, ...],
    existing_assignment_stability_priority: int,
    lower_weekly_load_priority: int,
    continuity_priority: int,
    assignment_id_factory: AssignmentIdFactory,
    created_at: datetime,
    repository: WeeklyWorkforceProposalRepository,
) -> ComposedWeeklyWorkforceProposal:
    previous = repository.get_revision(
        organization_id=organization_id,
        proposal_id=proposal_id,
        version=previous_version,
    )
    generation_result = generate_weekly_proposal_baseline(
        snapshot=snapshot,
        capability_mappings=capability_mappings,
        existing_assignment_stability_priority=(
            existing_assignment_stability_priority
        ),
        lower_weekly_load_priority=lower_weekly_load_priority,
        continuity_priority=continuity_priority,
        assignment_id_factory=assignment_id_factory,
    )
    new_revision = compose_next_weekly_proposal_revision(
        previous=previous,
        snapshot=snapshot,
        generation_result=generation_result,
        created_at=created_at,
    )
    latest = repository.latest_revision(
        organization_id=organization_id,
        proposal_id=proposal_id,
    )
    if latest.proposal.version != previous_version:
        raise WeeklyProposalRegenerationStaleRevisionError(
            "previous proposal revision is stale"
        )
    return repository.save_revision(
        organization_id=organization_id,
        snapshot=snapshot,
        aggregate=new_revision,
    )
