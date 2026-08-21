from app.domain.workforce_auto_planning.constraint_evaluation import (
    ConstraintEvidence,
)
from app.domain.workforce_auto_planning.planning_preference import (
    PlanningPreferenceEvaluation,
    PlanningPreferenceOutcome,
)
from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    WorkforceCandidateSnapshot,
)


_CODE = "continuity"
_RULE_ORIGIN = "core-policy"


def evaluate_continuity_preference(
    *,
    candidate: WorkforceCandidateSnapshot,
    compared_candidate: WorkforceCandidateSnapshot,
    priority: int,
) -> PlanningPreferenceEvaluation:
    candidate_consecutivity = candidate.recent_consecutivity
    compared_consecutivity = compared_candidate.recent_consecutivity
    evidence = (
        ConstraintEvidence(
            key="candidate-recent-consecutivity",
            value=candidate_consecutivity,
        ),
        ConstraintEvidence(
            key="compared-candidate-recent-consecutivity",
            value=compared_consecutivity,
        ),
    )

    if candidate_consecutivity is None or compared_consecutivity is None:
        outcome = PlanningPreferenceOutcome.NEUTRAL
        message = (
            "Continuity comparison is unavailable because recent "
            "consecutivity is unknown."
        )
    elif candidate_consecutivity < compared_consecutivity:
        outcome = PlanningPreferenceOutcome.PREFERRED
        message = "Candidate has lower recent consecutivity."
    elif candidate_consecutivity > compared_consecutivity:
        outcome = PlanningPreferenceOutcome.DEPRIORITIZED
        message = "Candidate has higher recent consecutivity."
    else:
        outcome = PlanningPreferenceOutcome.NEUTRAL
        message = "Candidates have equal recent consecutivity."

    return PlanningPreferenceEvaluation(
        code=_CODE,
        outcome=outcome,
        priority=priority,
        message=message,
        evidence=evidence,
        rule_origin=_RULE_ORIGIN,
    )
