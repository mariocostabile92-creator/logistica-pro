from collections.abc import Callable

from app.domain.workforce_auto_planning.constraint_evaluation import (
    ConstraintEvidence,
)
from app.domain.workforce_auto_planning.continuity_preference import (
    evaluate_continuity_preference,
)
from app.domain.workforce_auto_planning.existing_assignment_stability_preference import (
    evaluate_existing_assignment_stability_preference,
)
from app.domain.workforce_auto_planning.lower_weekly_load_preference import (
    evaluate_lower_weekly_load_preference,
)
from app.domain.workforce_auto_planning.operational_demand import (
    OperationalDemand,
)
from app.domain.workforce_auto_planning.operational_demand_trace import (
    compute_operational_demand_trace_id,
)
from app.domain.workforce_auto_planning.planning_preference import (
    PlanningPreferenceEvaluation,
    PlanningPreferenceOutcome,
    WorkforcePlanningPreferenceSet,
)
from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    WorkforceCandidateSnapshot,
)


_RULE_ORIGIN = "core-policy"
_OUTCOME_PRECEDENCE = (
    PlanningPreferenceOutcome.DEPRIORITIZED,
    PlanningPreferenceOutcome.PREFERRED,
    PlanningPreferenceOutcome.NEUTRAL,
)

PairwisePreferenceEvaluator = Callable[..., PlanningPreferenceEvaluation]


def _aggregate_outcome(
    evaluations: tuple[PlanningPreferenceEvaluation, ...],
) -> PlanningPreferenceOutcome:
    observed = {evaluation.outcome for evaluation in evaluations}
    return next(
        outcome for outcome in _OUTCOME_PRECEDENCE if outcome in observed
    ) if observed else PlanningPreferenceOutcome.NEUTRAL


def _aggregate_message(
    *,
    code: str,
    outcome: PlanningPreferenceOutcome,
) -> str:
    label = code.replace("-", " ").capitalize()
    messages = {
        PlanningPreferenceOutcome.DEPRIORITIZED: (
            f"{label} is deprioritized by at least one cohort comparison."
        ),
        PlanningPreferenceOutcome.PREFERRED: (
            f"{label} is preferred by at least one cohort comparison and "
            "deprioritized by none."
        ),
        PlanningPreferenceOutcome.NEUTRAL: (
            f"{label} is neutral across all cohort comparisons."
        ),
    }
    return messages[outcome]


def _aggregate_evidence(
    *,
    comparisons: tuple[
        tuple[WorkforceCandidateSnapshot, PlanningPreferenceEvaluation], ...
    ],
) -> tuple[ConstraintEvidence, ...]:
    counts = {
        outcome: sum(
            evaluation.outcome == outcome
            for _candidate, evaluation in comparisons
        )
        for outcome in PlanningPreferenceOutcome
    }
    evidence: list[ConstraintEvidence] = [
        ConstraintEvidence(key="comparison-count", value=len(comparisons)),
        ConstraintEvidence(
            key="preferred-count",
            value=counts[PlanningPreferenceOutcome.PREFERRED],
        ),
        ConstraintEvidence(
            key="neutral-count",
            value=counts[PlanningPreferenceOutcome.NEUTRAL],
        ),
        ConstraintEvidence(
            key="deprioritized-count",
            value=counts[PlanningPreferenceOutcome.DEPRIORITIZED],
        ),
    ]
    for index, (compared_candidate, evaluation) in enumerate(
        comparisons,
        start=1,
    ):
        prefix = f"comparison-{index}"
        evidence.extend(
            (
                ConstraintEvidence(
                    key=f"{prefix}:workforce-member-id",
                    value=compared_candidate.workforce_member_id,
                ),
                ConstraintEvidence(
                    key=f"{prefix}:outcome",
                    value=evaluation.outcome.value,
                ),
            )
        )
        evidence.extend(
            ConstraintEvidence(
                key=f"{prefix}:{item.key}",
                value=item.value,
            )
            for item in evaluation.evidence
        )
    return tuple(evidence)


def _compose_pairwise_preference(
    *,
    candidate: WorkforceCandidateSnapshot,
    cohort: tuple[WorkforceCandidateSnapshot, ...],
    priority: int,
    evaluator: PairwisePreferenceEvaluator,
    code: str,
) -> PlanningPreferenceEvaluation:
    comparisons = tuple(
        (
            compared_candidate,
            evaluator(
                candidate=candidate,
                compared_candidate=compared_candidate,
                priority=priority,
            ),
        )
        for compared_candidate in cohort
        if compared_candidate.workforce_member_id
        != candidate.workforce_member_id
    )
    outcome = _aggregate_outcome(
        tuple(evaluation for _candidate, evaluation in comparisons)
    )
    return PlanningPreferenceEvaluation(
        code=code,
        outcome=outcome,
        priority=priority,
        message=_aggregate_message(code=code, outcome=outcome),
        evidence=_aggregate_evidence(comparisons=comparisons),
        rule_origin=_RULE_ORIGIN,
    )


def build_baseline_workforce_preference_sets(
    *,
    candidates: tuple[WorkforceCandidateSnapshot, ...],
    demand: OperationalDemand,
    existing_assignment_stability_priority: int,
    lower_weekly_load_priority: int,
    continuity_priority: int,
) -> tuple[WorkforcePlanningPreferenceSet, ...]:
    cohort = tuple(
        sorted(
            candidates,
            key=lambda candidate: candidate.workforce_member_id,
        )
    )
    member_ids = [candidate.workforce_member_id for candidate in cohort]
    if len(member_ids) != len(set(member_ids)):
        raise ValueError("duplicate workforce member in preference cohort")

    demand_trace_id = compute_operational_demand_trace_id(demand)
    return tuple(
        WorkforcePlanningPreferenceSet(
            demand_trace_id=demand_trace_id,
            workforce_member_id=candidate.workforce_member_id,
            operational_date=demand.date,
            evaluations=(
                evaluate_existing_assignment_stability_preference(
                    candidate=candidate,
                    demand=demand,
                    priority=existing_assignment_stability_priority,
                ),
                _compose_pairwise_preference(
                    candidate=candidate,
                    cohort=cohort,
                    priority=lower_weekly_load_priority,
                    evaluator=evaluate_lower_weekly_load_preference,
                    code="lower-weekly-load",
                ),
                _compose_pairwise_preference(
                    candidate=candidate,
                    cohort=cohort,
                    priority=continuity_priority,
                    evaluator=evaluate_continuity_preference,
                    code="continuity",
                ),
            ),
        )
        for candidate in cohort
    )
