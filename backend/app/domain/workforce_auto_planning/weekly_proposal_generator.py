from datetime import date as CalendarDate, time
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.domain.core_language import OperationalUnit, TimeWindow
from app.domain.workforce_auto_planning.baseline_preference_composer import (
    build_baseline_workforce_preference_sets,
)
from app.domain.workforce_auto_planning.candidate_ranking import (
    RankedWorkforceCandidate,
    WorkforceCandidateRankingInput,
    rank_eligible_workforce_candidates,
)
from app.domain.workforce_auto_planning.coverage_gap import (
    CoverageGap,
    CoverageGapReason,
)
from app.domain.workforce_auto_planning.operational_demand import (
    OperationalDemand,
)
from app.domain.workforce_auto_planning.planning_policy import (
    WorkloadCapabilityMapping,
)
from app.domain.workforce_auto_planning.planning_preference import (
    WorkforcePlanningPreferenceSet,
)
from app.domain.workforce_auto_planning.proposed_shift_assignment import (
    ProposedAssignmentReason,
    ProposedShiftAssignment,
    ProposedShiftAssignmentOrigin,
    ProposedShiftAssignmentStatus,
)
from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    WeeklyPlanningInputSnapshot,
    WorkforceCandidateSnapshot,
)
from app.domain.workforce_auto_planning.workforce_eligibility_decision import (
    WorkforceEligibilityDecision,
)
from app.domain.workforce_auto_planning.workforce_eligibility_evaluator import (
    evaluate_workforce_candidate_eligibility,
)


class AssignmentIdFactory(Protocol):
    def __call__(
        self,
        *,
        organization_id: str,
        workforce_member_id: str,
        operational_date: CalendarDate,
        operational_unit: OperationalUnit,
        time_window: TimeWindow,
        capability_or_workload: str,
        deterministic_priority: int,
    ) -> str: ...


class WeeklyProposalGenerationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    assignments: tuple[ProposedShiftAssignment, ...] = Field(
        default_factory=tuple
    )
    coverage_gaps: tuple[CoverageGap, ...] = Field(default_factory=tuple)
    eligibility_decisions: tuple[WorkforceEligibilityDecision, ...] = Field(
        default_factory=tuple
    )
    preference_sets: tuple[WorkforcePlanningPreferenceSet, ...] = Field(
        default_factory=tuple
    )
    ranked_candidates: tuple[RankedWorkforceCandidate, ...] = Field(
        default_factory=tuple
    )


class _IntraRunConflictStatus(str, Enum):
    NO_CONFLICT = "NO_CONFLICT"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"


def _parse_time_window(window: TimeWindow) -> tuple[time, time] | None:
    if window.starts_at is None or window.ends_at is None:
        return None
    try:
        start = time.fromisoformat(window.starts_at)
        end = time.fromisoformat(window.ends_at)
    except ValueError:
        return None
    if start.tzinfo is not None or end.tzinfo is not None or end <= start:
        return None
    return start, end


def _intra_run_conflict(
    *,
    assignment: ProposedShiftAssignment,
    demand: OperationalDemand,
) -> _IntraRunConflictStatus:
    if assignment.date != demand.date:
        return _IntraRunConflictStatus.NO_CONFLICT
    assignment_window = _parse_time_window(assignment.time_window)
    demand_window = _parse_time_window(demand.time_window)
    if assignment_window is None or demand_window is None:
        return _IntraRunConflictStatus.UNKNOWN
    assignment_start, assignment_end = assignment_window
    demand_start, demand_end = demand_window
    if assignment_start < demand_end and demand_start < assignment_end:
        return _IntraRunConflictStatus.CONFLICT
    return _IntraRunConflictStatus.NO_CONFLICT


def _demand_ordering_key(
    demand: OperationalDemand,
) -> tuple[CalendarDate, str, str, str, str, str, str, int, int]:
    return (
        demand.date,
        demand.time_window.external_identifier,
        demand.capability_or_workload,
        demand.source,
        demand.operational_unit.external_identifier,
        demand.time_window.starts_at or "",
        demand.time_window.ends_at or "",
        demand.base_quantity,
        demand.target_quantity,
    )


def _ordered_candidates(
    snapshot: WeeklyPlanningInputSnapshot,
) -> tuple[WorkforceCandidateSnapshot, ...]:
    candidates = tuple(
        sorted(
            snapshot.workforce_candidates,
            key=lambda candidate: candidate.workforce_member_id,
        )
    )
    member_ids = [candidate.workforce_member_id for candidate in candidates]
    if len(member_ids) != len(set(member_ids)):
        raise ValueError("duplicate workforce member in planning snapshot")
    return candidates


def _assignment_reasons(
    ranked: RankedWorkforceCandidate,
) -> tuple[ProposedAssignmentReason, ...]:
    return (
        ProposedAssignmentReason(
            code="candidate-eligible",
            message="Candidate passed all baseline hard constraints.",
        ),
        ProposedAssignmentReason(
            code="deterministic-rank",
            message=f"Candidate selected at deterministic rank {ranked.rank}.",
        ),
        *(
            ProposedAssignmentReason(
                code=f"preference-{evaluation.code}",
                message=(
                    f"Baseline preference {evaluation.code}: "
                    f"{evaluation.outcome.value}."
                ),
            )
            for evaluation in ranked.preference_set.evaluations
        ),
    )


def _gap_reason(
    *,
    required_quantity: int,
    proposed_quantity: int,
    eligible_cohort_size: int,
    intra_run_conflict_skips: int,
) -> CoverageGapReason:
    complete = required_quantity == proposed_quantity
    return CoverageGapReason(
        code=(
            "complete-proposed-coverage"
            if complete
            else "insufficient-proposed-coverage"
        ),
        message=(
            f"Required quantity: {required_quantity}; proposed quantity: "
            f"{proposed_quantity}; eligible cohort size: "
            f"{eligible_cohort_size}; skipped for intra-run conflict: "
            f"{intra_run_conflict_skips}."
        ),
    )


def generate_weekly_proposal_baseline(
    *,
    snapshot: WeeklyPlanningInputSnapshot,
    capability_mappings: tuple[WorkloadCapabilityMapping, ...],
    existing_assignment_stability_priority: int,
    lower_weekly_load_priority: int,
    continuity_priority: int,
    assignment_id_factory: AssignmentIdFactory,
) -> WeeklyProposalGenerationResult:
    candidates = _ordered_candidates(snapshot)
    demands = tuple(sorted(snapshot.demands, key=_demand_ordering_key))
    assignments: list[ProposedShiftAssignment] = []
    coverage_gaps: list[CoverageGap] = []
    all_decisions: list[WorkforceEligibilityDecision] = []
    all_preference_sets: list[WorkforcePlanningPreferenceSet] = []
    all_ranked_candidates: list[RankedWorkforceCandidate] = []

    for demand in demands:
        decisions = tuple(
            evaluate_workforce_candidate_eligibility(
                candidate=candidate,
                demand=demand,
                capability_mappings=capability_mappings,
            )
            for candidate in candidates
        )
        all_decisions.extend(decisions)
        decisions_by_member = {
            decision.workforce_member_id: decision for decision in decisions
        }
        eligible_candidates = tuple(
            candidate
            for candidate in candidates
            if decisions_by_member[candidate.workforce_member_id].eligible
        )
        preference_sets = build_baseline_workforce_preference_sets(
            candidates=eligible_candidates,
            demand=demand,
            existing_assignment_stability_priority=(
                existing_assignment_stability_priority
            ),
            lower_weekly_load_priority=lower_weekly_load_priority,
            continuity_priority=continuity_priority,
        )
        all_preference_sets.extend(preference_sets)
        preferences_by_member = {
            item.workforce_member_id: item for item in preference_sets
        }
        ranking_inputs = tuple(
            WorkforceCandidateRankingInput(
                candidate=candidate,
                eligibility_decision=(
                    decisions_by_member[candidate.workforce_member_id]
                ),
                preference_set=preferences_by_member[
                    candidate.workforce_member_id
                ],
            )
            for candidate in eligible_candidates
        )
        ranked_candidates = rank_eligible_workforce_candidates(
            candidates=ranking_inputs
        )
        all_ranked_candidates.extend(ranked_candidates)

        generated_for_demand: list[ProposedShiftAssignment] = []
        intra_run_conflict_skips = 0
        for ranked in ranked_candidates:
            if len(generated_for_demand) >= demand.target_quantity:
                break
            member_assignments = tuple(
                assignment
                for assignment in assignments
                if assignment.workforce_member_id
                == ranked.workforce_member_id
            )
            conflict_statuses = tuple(
                _intra_run_conflict(assignment=assignment, demand=demand)
                for assignment in member_assignments
            )
            if any(
                status
                in {
                    _IntraRunConflictStatus.CONFLICT,
                    _IntraRunConflictStatus.UNKNOWN,
                }
                for status in conflict_statuses
            ):
                intra_run_conflict_skips += 1
                continue

            assignment = ProposedShiftAssignment(
                assignment_id=assignment_id_factory(
                    organization_id=demand.organization_id,
                    workforce_member_id=ranked.workforce_member_id,
                    operational_date=demand.date,
                    operational_unit=demand.operational_unit,
                    time_window=demand.time_window,
                    capability_or_workload=demand.capability_or_workload,
                    deterministic_priority=ranked.rank,
                ),
                organization_id=demand.organization_id,
                workforce_member_id=ranked.workforce_member_id,
                date=demand.date,
                operational_unit=demand.operational_unit,
                shift_identifier=None,
                time_window=demand.time_window,
                capability_or_workload=demand.capability_or_workload,
                origin=ProposedShiftAssignmentOrigin.AUTOMATIC,
                status=ProposedShiftAssignmentStatus.PROPOSED,
                deterministic_priority=ranked.rank,
                reasons=_assignment_reasons(ranked),
                locked=False,
            )
            generated_for_demand.append(assignment)
            assignments.append(assignment)

        proposed_quantity = len(generated_for_demand)
        excluded_categories = {
            evaluation.code
            for decision in decisions
            if not decision.eligible
            for evaluation in decision.evaluations
            if not evaluation.passed
        }
        if intra_run_conflict_skips:
            excluded_categories.add("intra-run-conflict")
        coverage_gaps.append(
            CoverageGap(
                organization_id=demand.organization_id,
                date=demand.date,
                operational_unit=demand.operational_unit,
                time_window=demand.time_window,
                capability_or_workload=demand.capability_or_workload,
                required_quantity=demand.target_quantity,
                proposed_quantity=proposed_quantity,
                gap_quantity=demand.target_quantity - proposed_quantity,
                reason=_gap_reason(
                    required_quantity=demand.target_quantity,
                    proposed_quantity=proposed_quantity,
                    eligible_cohort_size=len(eligible_candidates),
                    intra_run_conflict_skips=intra_run_conflict_skips,
                ),
                excluded_candidate_categories=tuple(
                    sorted(excluded_categories)
                ),
            )
        )

    return WeeklyProposalGenerationResult(
        assignments=tuple(assignments),
        coverage_gaps=tuple(coverage_gaps),
        eligibility_decisions=tuple(all_decisions),
        preference_sets=tuple(all_preference_sets),
        ranked_candidates=tuple(all_ranked_candidates),
    )
