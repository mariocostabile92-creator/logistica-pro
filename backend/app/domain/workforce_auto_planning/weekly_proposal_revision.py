from datetime import datetime

from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    WeeklyPlanningInputSnapshot,
)
from app.domain.workforce_auto_planning.weekly_proposal_composer import (
    ComposedWeeklyWorkforceProposal,
    compose_weekly_workforce_proposal,
)
from app.domain.workforce_auto_planning.weekly_proposal_generator import (
    WeeklyProposalGenerationResult,
)


class WeeklyProposalRevisionCompositionError(ValueError):
    pass


def compose_next_weekly_proposal_revision(
    *,
    previous: ComposedWeeklyWorkforceProposal,
    snapshot: WeeklyPlanningInputSnapshot,
    generation_result: WeeklyProposalGenerationResult,
    created_at: datetime,
) -> ComposedWeeklyWorkforceProposal:
    previous_proposal = previous.proposal
    scope_checks = (
        (
            snapshot.organization_id == previous_proposal.organization_id,
            "snapshot organization does not match previous proposal",
        ),
        (
            snapshot.period_start == previous_proposal.period_start,
            "snapshot period_start does not match previous proposal",
        ),
        (
            snapshot.period_end == previous_proposal.period_end,
            "snapshot period_end does not match previous proposal",
        ),
        (
            snapshot.operational_unit.external_identifier
            == previous_proposal.operational_unit.external_identifier,
            "snapshot operational unit does not match previous proposal",
        ),
    )
    for matches, message in scope_checks:
        if not matches:
            raise WeeklyProposalRevisionCompositionError(message)

    return compose_weekly_workforce_proposal(
        snapshot=snapshot,
        generation_result=generation_result,
        proposal_id=previous_proposal.proposal_id,
        version=previous_proposal.version + 1,
        created_at=created_at,
    )
