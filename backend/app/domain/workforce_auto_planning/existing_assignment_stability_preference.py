from datetime import time

from app.domain.workforce_auto_planning.constraint_evaluation import (
    ConstraintEvidence,
)
from app.domain.workforce_auto_planning.operational_demand import (
    OperationalDemand,
)
from app.domain.workforce_auto_planning.planning_preference import (
    PlanningPreferenceEvaluation,
    PlanningPreferenceOutcome,
)
from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    ApprovedAssignmentSnapshot,
    WorkforceCandidateSnapshot,
)


_CODE = "existing-assignment-stability"
_RULE_ORIGIN = "core-policy"


def _is_valid_window(starts_at: str | None, ends_at: str | None) -> bool:
    if starts_at is None or ends_at is None:
        return False
    try:
        start = time.fromisoformat(starts_at)
        end = time.fromisoformat(ends_at)
    except ValueError:
        return False
    return (
        start.tzinfo is None
        and end.tzinfo is None
        and end > start
    )


def _assignment_sort_key(
    assignment: ApprovedAssignmentSnapshot,
) -> tuple[str, str, str, str, str]:
    return (
        assignment.date.isoformat(),
        assignment.assignment_reference,
        assignment.time_window.starts_at or "",
        assignment.time_window.ends_at or "",
        (
            assignment.operational_unit.external_identifier
            if assignment.operational_unit is not None
            else ""
        ),
    )


def _is_compatible(
    assignment: ApprovedAssignmentSnapshot,
    demand: OperationalDemand,
) -> bool:
    assignment_window = assignment.time_window
    demand_window = demand.time_window
    if assignment.date != demand.date:
        return False
    if not _is_valid_window(
        assignment_window.starts_at,
        assignment_window.ends_at,
    ) or not _is_valid_window(
        demand_window.starts_at,
        demand_window.ends_at,
    ):
        return False
    if (
        assignment_window.starts_at != demand_window.starts_at
        or assignment_window.ends_at != demand_window.ends_at
    ):
        return False
    if assignment.operational_unit is None:
        return False
    return (
        assignment.operational_unit.external_identifier
        == demand.operational_unit.external_identifier
    )


def evaluate_existing_assignment_stability_preference(
    *,
    candidate: WorkforceCandidateSnapshot,
    demand: OperationalDemand,
    priority: int,
) -> PlanningPreferenceEvaluation:
    assignments = tuple(
        sorted(
            candidate.already_approved_assignments,
            key=_assignment_sort_key,
        )
    )
    compatible_assignment = next(
        (
            assignment
            for assignment in assignments
            if _is_compatible(assignment, demand)
        ),
        None,
    )
    compatible = compatible_assignment is not None
    evidence = (
        ConstraintEvidence(
            key="evaluated-assignment-count",
            value=len(assignments),
        ),
        ConstraintEvidence(
            key="demand-date",
            value=demand.date.isoformat(),
        ),
        ConstraintEvidence(
            key="demand-start",
            value=demand.time_window.starts_at,
        ),
        ConstraintEvidence(
            key="demand-end",
            value=demand.time_window.ends_at,
        ),
        ConstraintEvidence(
            key="demand-operational-unit",
            value=demand.operational_unit.external_identifier,
        ),
        ConstraintEvidence(
            key="compatible-assignment-reference",
            value=(
                compatible_assignment.assignment_reference
                if compatible_assignment is not None
                else None
            ),
        ),
        ConstraintEvidence(
            key="compatible-assignment-date",
            value=(
                compatible_assignment.date.isoformat()
                if compatible_assignment is not None
                else None
            ),
        ),
        ConstraintEvidence(
            key="compatible-assignment-start",
            value=(
                compatible_assignment.time_window.starts_at
                if compatible_assignment is not None
                else None
            ),
        ),
        ConstraintEvidence(
            key="compatible-assignment-end",
            value=(
                compatible_assignment.time_window.ends_at
                if compatible_assignment is not None
                else None
            ),
        ),
        ConstraintEvidence(
            key="compatible-assignment-operational-unit",
            value=(
                compatible_assignment.operational_unit.external_identifier
                if compatible_assignment is not None
                and compatible_assignment.operational_unit is not None
                else None
            ),
        ),
        ConstraintEvidence(
            key="decision-reason",
            value=(
                "compatible-assignment-found"
                if compatible
                else "no-authoritative-compatible-assignment"
            ),
        ),
    )
    return PlanningPreferenceEvaluation(
        code=_CODE,
        outcome=(
            PlanningPreferenceOutcome.PREFERRED
            if compatible
            else PlanningPreferenceOutcome.NEUTRAL
        ),
        priority=priority,
        message=(
            "An approved assignment exactly matches the demand."
            if compatible
            else "No approved assignment authoritatively matches the demand."
        ),
        evidence=evidence,
        rule_origin=_RULE_ORIGIN,
    )
