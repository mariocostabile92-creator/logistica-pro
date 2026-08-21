from decimal import Decimal

from app.domain.workforce_auto_planning.constraint_evaluation import (
    ConstraintEvidence,
)
from app.domain.workforce_auto_planning.planning_preference import (
    PlanningPreferenceEvaluation,
    PlanningPreferenceOutcome,
)
from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    AssignedTimeSnapshot,
    AssignedTimeStatus,
    AssignedTimeUnit,
    WorkforceCandidateSnapshot,
)


_CODE = "lower-weekly-load"
_RULE_ORIGIN = "core-policy"


def _decimal_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _normalized_minutes(assigned_time: AssignedTimeSnapshot) -> Decimal | None:
    if assigned_time.status != AssignedTimeStatus.KNOWN:
        return None
    if assigned_time.unit == AssignedTimeUnit.MINUTES:
        return assigned_time.value
    if assigned_time.unit == AssignedTimeUnit.HOURS:
        return assigned_time.value * Decimal("60")
    return None


def _assigned_time_evidence(
    *,
    prefix: str,
    assigned_time: AssignedTimeSnapshot,
    normalized_minutes: Decimal | None,
) -> tuple[ConstraintEvidence, ...]:
    return (
        ConstraintEvidence(
            key=f"{prefix}-assigned-status",
            value=assigned_time.status.value,
        ),
        ConstraintEvidence(
            key=f"{prefix}-assigned-quantity",
            value=_decimal_text(assigned_time.value),
        ),
        ConstraintEvidence(
            key=f"{prefix}-assigned-unit",
            value=(
                assigned_time.unit.value
                if assigned_time.unit is not None
                else None
            ),
        ),
        ConstraintEvidence(
            key=f"{prefix}-normalized-minutes",
            value=_decimal_text(normalized_minutes),
        ),
    )


def evaluate_lower_weekly_load_preference(
    *,
    candidate: WorkforceCandidateSnapshot,
    compared_candidate: WorkforceCandidateSnapshot,
    priority: int,
) -> PlanningPreferenceEvaluation:
    candidate_assigned = candidate.already_assigned_minutes_or_hours
    compared_assigned = compared_candidate.already_assigned_minutes_or_hours
    candidate_minutes = _normalized_minutes(candidate_assigned)
    compared_minutes = _normalized_minutes(compared_assigned)
    evidence = (
        *_assigned_time_evidence(
            prefix="candidate",
            assigned_time=candidate_assigned,
            normalized_minutes=candidate_minutes,
        ),
        *_assigned_time_evidence(
            prefix="compared-candidate",
            assigned_time=compared_assigned,
            normalized_minutes=compared_minutes,
        ),
    )

    if candidate_minutes is None or compared_minutes is None:
        outcome = PlanningPreferenceOutcome.NEUTRAL
        message = (
            "Weekly load comparison is unavailable because assigned time "
            "is partial or unknown."
        )
    elif candidate_minutes < compared_minutes:
        outcome = PlanningPreferenceOutcome.PREFERRED
        message = "Candidate has a lower known weekly load."
    elif candidate_minutes > compared_minutes:
        outcome = PlanningPreferenceOutcome.DEPRIORITIZED
        message = "Candidate has a higher known weekly load."
    else:
        outcome = PlanningPreferenceOutcome.NEUTRAL
        message = "Candidates have an equal known weekly load."

    return PlanningPreferenceEvaluation(
        code=_CODE,
        outcome=outcome,
        priority=priority,
        message=message,
        evidence=evidence,
        rule_origin=_RULE_ORIGIN,
    )
