from datetime import date as CalendarDate, datetime

from pydantic import BaseModel, ConfigDict

from app.domain.core_language import OperationalUnit
from app.domain.workforce_auto_planning.candidate_ranking import (
    RankedWorkforceCandidate,
)
from app.domain.workforce_auto_planning.coverage_gap import CoverageGap
from app.domain.workforce_auto_planning.planning_preference import (
    WorkforcePlanningPreferenceSet,
)
from app.domain.workforce_auto_planning.operational_demand_trace import (
    compute_operational_demand_trace_id,
)
from app.domain.workforce_auto_planning.proposed_shift_assignment import (
    ProposedShiftAssignment,
)
from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    WeeklyPlanningInputSnapshot,
)
from app.domain.workforce_auto_planning.weekly_proposal_generator import (
    WeeklyProposalGenerationResult,
)
from app.domain.workforce_auto_planning.weekly_workforce_proposal import (
    WeeklyWorkforceProposal,
    WeeklyWorkforceProposalStatus,
)
from app.domain.workforce_auto_planning.workforce_eligibility_decision import (
    WorkforceEligibilityDecision,
)


class WeeklyProposalCompositionError(ValueError):
    pass


class ComposedWeeklyWorkforceProposal(BaseModel):
    model_config = ConfigDict(frozen=True)

    proposal: WeeklyWorkforceProposal
    assignments: tuple[ProposedShiftAssignment, ...]
    coverage_gaps: tuple[CoverageGap, ...]
    eligibility_decisions: tuple[WorkforceEligibilityDecision, ...]
    preference_sets: tuple[WorkforcePlanningPreferenceSet, ...]
    ranked_candidates: tuple[RankedWorkforceCandidate, ...]


def _validate_organization(
    *,
    actual: str,
    expected: str,
    subject: str,
) -> None:
    if actual != expected:
        raise WeeklyProposalCompositionError(
            f"{subject} organization does not match snapshot"
        )


def _validate_period(
    *,
    actual: CalendarDate,
    period_start: CalendarDate,
    period_end: CalendarDate,
    subject: str,
) -> None:
    if not period_start <= actual <= period_end:
        raise WeeklyProposalCompositionError(
            f"{subject} date falls outside snapshot period"
        )


def _validate_unit(
    *,
    actual: OperationalUnit,
    expected: OperationalUnit,
    subject: str,
) -> None:
    if actual.external_identifier != expected.external_identifier:
        raise WeeklyProposalCompositionError(
            f"{subject} operational unit does not match snapshot"
        )


def _validate_member(
    *,
    workforce_member_id: str,
    snapshot_member_ids: frozenset[str],
    subject: str,
) -> None:
    if workforce_member_id not in snapshot_member_ids:
        raise WeeklyProposalCompositionError(
            f"{subject} workforce member is not present in snapshot"
        )


def _validate_demand_trace(
    *,
    demand_trace_id: str,
    snapshot_demand_trace_ids: frozenset[str],
    subject: str,
) -> None:
    if demand_trace_id not in snapshot_demand_trace_ids:
        raise WeeklyProposalCompositionError(
            f"{subject} demand trace is not present in snapshot"
        )


def _validate_decision(
    *,
    decision: WorkforceEligibilityDecision,
    snapshot: WeeklyPlanningInputSnapshot,
    snapshot_member_ids: frozenset[str],
    snapshot_demand_trace_ids: frozenset[str],
    subject: str = "eligibility decision",
) -> None:
    _validate_demand_trace(
        demand_trace_id=decision.demand_trace_id,
        snapshot_demand_trace_ids=snapshot_demand_trace_ids,
        subject=subject,
    )
    _validate_organization(
        actual=decision.organization_id,
        expected=snapshot.organization_id,
        subject=subject,
    )
    _validate_period(
        actual=decision.operational_date,
        period_start=snapshot.period_start,
        period_end=snapshot.period_end,
        subject=subject,
    )
    _validate_unit(
        actual=decision.operational_unit,
        expected=snapshot.operational_unit,
        subject=subject,
    )
    _validate_member(
        workforce_member_id=decision.workforce_member_id,
        snapshot_member_ids=snapshot_member_ids,
        subject=subject,
    )


def _validate_preference_set(
    *,
    preference_set: WorkforcePlanningPreferenceSet,
    snapshot: WeeklyPlanningInputSnapshot,
    snapshot_member_ids: frozenset[str],
    snapshot_demand_trace_ids: frozenset[str],
    subject: str = "preference set",
) -> None:
    _validate_demand_trace(
        demand_trace_id=preference_set.demand_trace_id,
        snapshot_demand_trace_ids=snapshot_demand_trace_ids,
        subject=subject,
    )
    _validate_period(
        actual=preference_set.operational_date,
        period_start=snapshot.period_start,
        period_end=snapshot.period_end,
        subject=subject,
    )
    _validate_member(
        workforce_member_id=preference_set.workforce_member_id,
        snapshot_member_ids=snapshot_member_ids,
        subject=subject,
    )


def _validate_generation_result(
    *,
    snapshot: WeeklyPlanningInputSnapshot,
    generation_result: WeeklyProposalGenerationResult,
) -> None:
    snapshot_member_ids = frozenset(
        candidate.workforce_member_id
        for candidate in snapshot.workforce_candidates
    )
    snapshot_demand_trace_ids = frozenset(
        compute_operational_demand_trace_id(demand)
        for demand in snapshot.demands
    )
    for assignment in generation_result.assignments:
        _validate_demand_trace(
            demand_trace_id=assignment.demand_trace_id,
            snapshot_demand_trace_ids=snapshot_demand_trace_ids,
            subject="assignment",
        )
        _validate_organization(
            actual=assignment.organization_id,
            expected=snapshot.organization_id,
            subject="assignment",
        )
        _validate_period(
            actual=assignment.date,
            period_start=snapshot.period_start,
            period_end=snapshot.period_end,
            subject="assignment",
        )
        _validate_unit(
            actual=assignment.operational_unit,
            expected=snapshot.operational_unit,
            subject="assignment",
        )
        _validate_member(
            workforce_member_id=assignment.workforce_member_id,
            snapshot_member_ids=snapshot_member_ids,
            subject="assignment",
        )

    for gap in generation_result.coverage_gaps:
        _validate_demand_trace(
            demand_trace_id=gap.demand_trace_id,
            snapshot_demand_trace_ids=snapshot_demand_trace_ids,
            subject="coverage gap",
        )
        _validate_organization(
            actual=gap.organization_id,
            expected=snapshot.organization_id,
            subject="coverage gap",
        )
        _validate_period(
            actual=gap.date,
            period_start=snapshot.period_start,
            period_end=snapshot.period_end,
            subject="coverage gap",
        )
        _validate_unit(
            actual=gap.operational_unit,
            expected=snapshot.operational_unit,
            subject="coverage gap",
        )

    for decision in generation_result.eligibility_decisions:
        _validate_decision(
            decision=decision,
            snapshot=snapshot,
            snapshot_member_ids=snapshot_member_ids,
            snapshot_demand_trace_ids=snapshot_demand_trace_ids,
        )

    for preference_set in generation_result.preference_sets:
        _validate_preference_set(
            preference_set=preference_set,
            snapshot=snapshot,
            snapshot_member_ids=snapshot_member_ids,
            snapshot_demand_trace_ids=snapshot_demand_trace_ids,
        )

    for ranked in generation_result.ranked_candidates:
        _validate_demand_trace(
            demand_trace_id=ranked.demand_trace_id,
            snapshot_demand_trace_ids=snapshot_demand_trace_ids,
            subject="ranked candidate",
        )
        _validate_member(
            workforce_member_id=ranked.workforce_member_id,
            snapshot_member_ids=snapshot_member_ids,
            subject="ranked candidate",
        )
        if ranked.candidate.workforce_member_id != ranked.workforce_member_id:
            raise WeeklyProposalCompositionError(
                "ranked candidate member reference is inconsistent"
            )
        _validate_organization(
            actual=ranked.candidate.organization_id,
            expected=snapshot.organization_id,
            subject="ranked candidate",
        )
        _validate_decision(
            decision=ranked.eligibility_decision,
            snapshot=snapshot,
            snapshot_member_ids=snapshot_member_ids,
            snapshot_demand_trace_ids=snapshot_demand_trace_ids,
            subject="ranked candidate eligibility decision",
        )
        _validate_preference_set(
            preference_set=ranked.preference_set,
            snapshot=snapshot,
            snapshot_member_ids=snapshot_member_ids,
            snapshot_demand_trace_ids=snapshot_demand_trace_ids,
            subject="ranked candidate preference set",
        )


def compose_weekly_workforce_proposal(
    *,
    snapshot: WeeklyPlanningInputSnapshot,
    generation_result: WeeklyProposalGenerationResult,
    proposal_id: str,
    version: int,
    created_at: datetime,
) -> ComposedWeeklyWorkforceProposal:
    _validate_generation_result(
        snapshot=snapshot,
        generation_result=generation_result,
    )
    proposal = WeeklyWorkforceProposal(
        proposal_id=proposal_id,
        organization_id=snapshot.organization_id,
        period_start=snapshot.period_start,
        period_end=snapshot.period_end,
        operational_unit=snapshot.operational_unit,
        version=version,
        input_snapshot_id=snapshot.snapshot_id,
        input_fingerprint=snapshot.fingerprint,
        policy_set_identifier=snapshot.policy_set_identifier,
        policy_set_version=snapshot.policy_set_version,
        status=WeeklyWorkforceProposalStatus.GENERATED,
        created_at=created_at,
    )
    return ComposedWeeklyWorkforceProposal(
        proposal=proposal,
        assignments=generation_result.assignments,
        coverage_gaps=generation_result.coverage_gaps,
        eligibility_decisions=generation_result.eligibility_decisions,
        preference_sets=generation_result.preference_sets,
        ranked_candidates=generation_result.ranked_candidates,
    )
