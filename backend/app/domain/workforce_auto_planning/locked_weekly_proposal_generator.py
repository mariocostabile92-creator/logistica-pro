from datetime import date as CalendarDate

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
from app.domain.workforce_auto_planning.locked_assignment_preservation import (
    build_locked_assignment_preservation_set,
)
from app.domain.workforce_auto_planning.operational_demand import OperationalDemand
from app.domain.workforce_auto_planning.operational_demand_trace import (
    compute_operational_demand_trace_id,
)
from app.domain.workforce_auto_planning.planning_policy import (
    WorkloadCapabilityMapping,
)
from app.domain.workforce_auto_planning.planning_preference import (
    WorkforcePlanningPreferenceSet,
)
from app.domain.workforce_auto_planning.proposed_shift_assignment import (
    ProposedShiftAssignment,
    ProposedShiftAssignmentOrigin,
    ProposedShiftAssignmentStatus,
)
from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    WeeklyPlanningInputSnapshot,
)
from app.domain.workforce_auto_planning.weekly_proposal_composer import (
    ComposedWeeklyWorkforceProposal,
)
from app.domain.workforce_auto_planning.weekly_proposal_generator import (
    AssignmentIdFactory,
    WeeklyProposalGenerationResult,
    _assignment_reasons,
    _demand_ordering_key,
    _intra_run_conflict,
    _IntraRunConflictStatus,
    _ordered_candidates,
)
from app.domain.workforce_auto_planning.workforce_eligibility_decision import (
    WorkforceEligibilityDecision,
)
from app.domain.workforce_auto_planning.workforce_eligibility_evaluator import (
    evaluate_workforce_candidate_eligibility,
)


def _assignment_ordering_key(
    assignment: ProposedShiftAssignment,
) -> tuple[CalendarDate, str, str, str]:
    return (
        assignment.date,
        assignment.time_window.external_identifier,
        assignment.workforce_member_id,
        assignment.assignment_id,
    )


def _has_blocking_conflict(
    *,
    assignments: tuple[ProposedShiftAssignment, ...],
    demand: OperationalDemand,
) -> bool:
    return any(
        _intra_run_conflict(assignment=assignment, demand=demand)
        in {
            _IntraRunConflictStatus.CONFLICT,
            _IntraRunConflictStatus.UNKNOWN,
        }
        for assignment in assignments
    )


def _gap_reason(
    *,
    target_quantity: int,
    locked_count: int,
    generated_count: int,
    eligible_cohort_size: int,
    locked_reservation_skips: int,
    intra_run_conflict_skips: int,
) -> CoverageGapReason:
    proposed_quantity = locked_count + generated_count
    overcoverage = max(locked_count - target_quantity, 0)
    if overcoverage:
        code = "locked-overcoverage"
    elif proposed_quantity == target_quantity:
        code = "complete-proposed-coverage"
    else:
        code = "insufficient-proposed-coverage"
    return CoverageGapReason(
        code=code,
        message=(
            f"Required quantity: {target_quantity}; locked assignments: "
            f"{locked_count}; newly generated assignments: {generated_count}; "
            f"eligible cohort size: {eligible_cohort_size}; skipped for locked "
            f"reservation: {locked_reservation_skips}; skipped for intra-run "
            f"conflict: {intra_run_conflict_skips}; locked overcoverage: "
            f"{overcoverage}."
        ),
    )


def generate_weekly_proposal_preserving_locked(
    *,
    snapshot: WeeklyPlanningInputSnapshot,
    previous: ComposedWeeklyWorkforceProposal,
    capability_mappings: tuple[WorkloadCapabilityMapping, ...],
    existing_assignment_stability_priority: int,
    lower_weekly_load_priority: int,
    continuity_priority: int,
    assignment_id_factory: AssignmentIdFactory,
) -> WeeklyProposalGenerationResult:
    preservation = build_locked_assignment_preservation_set(
        previous=previous,
        snapshot=snapshot,
    )
    locked_assignments = preservation.assignments
    locked_coverage = {
        item.demand_trace_id: item for item in preservation.coverage_by_demand
    }
    candidates = _ordered_candidates(snapshot)
    demands = tuple(sorted(snapshot.demands, key=_demand_ordering_key))
    generated_assignments: list[ProposedShiftAssignment] = []
    all_decisions: list[WorkforceEligibilityDecision] = []
    all_preference_sets: list[WorkforcePlanningPreferenceSet] = []
    all_ranked_candidates: list[RankedWorkforceCandidate] = []
    run_context: dict[str, tuple[int, int, int, int]] = {}
    decisions_by_trace: dict[
        str, tuple[WorkforceEligibilityDecision, ...]
    ] = {}

    for demand in demands:
        demand_trace_id = compute_operational_demand_trace_id(demand)
        coverage = locked_coverage.get(demand_trace_id)
        locked_count = (
            coverage.locked_assignments_count if coverage is not None else 0
        )
        remaining_quantity = (
            coverage.remaining_quantity
            if coverage is not None
            else demand.target_quantity
        )
        if remaining_quantity == 0:
            run_context[demand_trace_id] = (0, 0, 0, 0)
            decisions_by_trace[demand_trace_id] = ()
            continue

        decisions = tuple(
            evaluate_workforce_candidate_eligibility(
                candidate=candidate,
                demand=demand,
                capability_mappings=capability_mappings,
            )
            for candidate in candidates
        )
        decisions_by_trace[demand_trace_id] = decisions
        all_decisions.extend(decisions)
        decision_by_member = {
            decision.workforce_member_id: decision for decision in decisions
        }
        eligible_candidates = tuple(
            candidate
            for candidate in candidates
            if decision_by_member[candidate.workforce_member_id].eligible
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
        preference_by_member = {
            item.workforce_member_id: item for item in preference_sets
        }
        ranked_candidates = rank_eligible_workforce_candidates(
            candidates=tuple(
                WorkforceCandidateRankingInput(
                    candidate=candidate,
                    eligibility_decision=decision_by_member[
                        candidate.workforce_member_id
                    ],
                    preference_set=preference_by_member[
                        candidate.workforce_member_id
                    ],
                )
                for candidate in eligible_candidates
            )
        )
        all_ranked_candidates.extend(ranked_candidates)

        generated_for_demand: list[ProposedShiftAssignment] = []
        locked_reservation_skips = 0
        intra_run_conflict_skips = 0
        for ranked in ranked_candidates:
            if len(generated_for_demand) >= remaining_quantity:
                break
            member_locked = tuple(
                assignment
                for assignment in locked_assignments
                if assignment.workforce_member_id == ranked.workforce_member_id
            )
            if _has_blocking_conflict(
                assignments=member_locked,
                demand=demand,
            ):
                locked_reservation_skips += 1
                continue
            member_generated = tuple(
                assignment
                for assignment in generated_assignments
                if assignment.workforce_member_id == ranked.workforce_member_id
            )
            if _has_blocking_conflict(
                assignments=member_generated,
                demand=demand,
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
                demand_trace_id=demand_trace_id,
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
            generated_assignments.append(assignment)

        run_context[demand_trace_id] = (
            len(generated_for_demand),
            len(eligible_candidates),
            locked_reservation_skips,
            intra_run_conflict_skips,
        )

    generated_count_by_trace: dict[str, int] = {}
    for assignment in generated_assignments:
        generated_count_by_trace[assignment.demand_trace_id] = (
            generated_count_by_trace.get(assignment.demand_trace_id, 0) + 1
        )
    gaps = []
    for demand in demands:
        demand_trace_id = compute_operational_demand_trace_id(demand)
        coverage = locked_coverage.get(demand_trace_id)
        locked_count = (
            coverage.locked_assignments_count if coverage is not None else 0
        )
        generated_count = generated_count_by_trace.get(demand_trace_id, 0)
        proposed_quantity = locked_count + generated_count
        _, eligible_size, locked_skips, intra_run_skips = run_context[
            demand_trace_id
        ]
        excluded_categories = {
            evaluation.code
            for decision in decisions_by_trace[demand_trace_id]
            if not decision.eligible
            for evaluation in decision.evaluations
            if not evaluation.passed
        }
        if locked_skips:
            excluded_categories.add("locked-reservation-conflict")
        if intra_run_skips:
            excluded_categories.add("intra-run-conflict")
        if locked_count > demand.target_quantity:
            excluded_categories.add("locked-overcoverage")
        gaps.append(
            CoverageGap(
                demand_trace_id=demand_trace_id,
                organization_id=demand.organization_id,
                date=demand.date,
                operational_unit=demand.operational_unit,
                time_window=demand.time_window,
                capability_or_workload=demand.capability_or_workload,
                required_quantity=demand.target_quantity,
                proposed_quantity=proposed_quantity,
                gap_quantity=demand.target_quantity - proposed_quantity,
                reason=_gap_reason(
                    target_quantity=demand.target_quantity,
                    locked_count=locked_count,
                    generated_count=generated_count,
                    eligible_cohort_size=eligible_size,
                    locked_reservation_skips=locked_skips,
                    intra_run_conflict_skips=intra_run_skips,
                ),
                excluded_candidate_categories=tuple(
                    sorted(excluded_categories)
                ),
            )
        )

    assignments = tuple(
        sorted(
            (*locked_assignments, *generated_assignments),
            key=_assignment_ordering_key,
        )
    )
    return WeeklyProposalGenerationResult(
        assignments=assignments,
        coverage_gaps=tuple(gaps),
        eligibility_decisions=tuple(all_decisions),
        preference_sets=tuple(all_preference_sets),
        ranked_candidates=tuple(all_ranked_candidates),
    )
