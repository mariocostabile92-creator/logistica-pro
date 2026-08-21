from datetime import time
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.domain.workforce_auto_planning.constraint_evaluation import (
    ConstraintEvidence,
)
from app.domain.workforce_auto_planning.operational_demand import (
    OperationalDemand,
)
from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    ApprovedAssignmentSnapshot,
)


class ApprovedAssignmentConflictStatus(str, Enum):
    NO_CONFLICT = "NO_CONFLICT"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"


class ApprovedAssignmentConflictReason(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ApprovedAssignmentConflictEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: ApprovedAssignmentConflictStatus
    reason: ApprovedAssignmentConflictReason
    evidence: tuple[ConstraintEvidence, ...] = Field(default_factory=tuple)


def _evidence(
    assignment: ApprovedAssignmentSnapshot,
    demand: OperationalDemand,
) -> tuple[ConstraintEvidence, ...]:
    return (
        ConstraintEvidence(
            key="assignment-date",
            value=assignment.date.isoformat(),
        ),
        ConstraintEvidence(
            key="demand-date",
            value=demand.date.isoformat(),
        ),
        ConstraintEvidence(
            key="assignment-start",
            value=assignment.time_window.starts_at,
        ),
        ConstraintEvidence(
            key="assignment-end",
            value=assignment.time_window.ends_at,
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
            key="assignment-operational-unit",
            value=(
                assignment.operational_unit.external_identifier
                if assignment.operational_unit is not None
                else None
            ),
        ),
        ConstraintEvidence(
            key="assignment-shift-identifier",
            value=assignment.shift_identifier,
        ),
    )


def _result(
    *,
    status: ApprovedAssignmentConflictStatus,
    code: str,
    message: str,
    evidence: tuple[ConstraintEvidence, ...],
) -> ApprovedAssignmentConflictEvaluation:
    return ApprovedAssignmentConflictEvaluation(
        status=status,
        reason=ApprovedAssignmentConflictReason(
            code=code,
            message=message,
        ),
        evidence=evidence,
    )


def _parse_time_window(
    starts_at: str,
    ends_at: str,
) -> tuple[time, time] | None:
    try:
        start = time.fromisoformat(starts_at)
        end = time.fromisoformat(ends_at)
    except ValueError:
        return None
    if start.tzinfo is not None or end.tzinfo is not None or end <= start:
        return None
    return start, end


def evaluate_approved_assignment_conflict(
    *,
    assignment: ApprovedAssignmentSnapshot,
    demand: OperationalDemand,
) -> ApprovedAssignmentConflictEvaluation:
    evidence = _evidence(assignment, demand)
    if assignment.date != demand.date:
        return _result(
            status=ApprovedAssignmentConflictStatus.NO_CONFLICT,
            code="different-date",
            message="Assignment and demand occur on different dates.",
            evidence=evidence,
        )

    endpoints = (
        assignment.time_window.starts_at,
        assignment.time_window.ends_at,
        demand.time_window.starts_at,
        demand.time_window.ends_at,
    )
    if any(endpoint is None for endpoint in endpoints):
        return _result(
            status=ApprovedAssignmentConflictStatus.UNKNOWN,
            code="incomplete-time-window",
            message="A complete time window is not available for comparison.",
            evidence=evidence,
        )

    assignment_window = _parse_time_window(endpoints[0], endpoints[1])
    demand_window = _parse_time_window(endpoints[2], endpoints[3])
    if assignment_window is None or demand_window is None:
        return _result(
            status=ApprovedAssignmentConflictStatus.UNKNOWN,
            code="unsupported-time-window",
            message="At least one time window cannot be interpreted.",
            evidence=evidence,
        )

    assignment_start, assignment_end = assignment_window
    demand_start, demand_end = demand_window
    overlaps = (
        assignment_start < demand_end
        and demand_start < assignment_end
    )
    if overlaps:
        return _result(
            status=ApprovedAssignmentConflictStatus.CONFLICT,
            code="overlapping-time-window",
            message="Assignment and demand time windows overlap.",
            evidence=evidence,
        )
    return _result(
        status=ApprovedAssignmentConflictStatus.NO_CONFLICT,
        code="no-overlap",
        message="Assignment and demand time windows do not overlap.",
        evidence=evidence,
    )
