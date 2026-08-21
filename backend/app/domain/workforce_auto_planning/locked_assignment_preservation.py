from datetime import date as CalendarDate, time
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.domain.core_language import TimeWindow
from app.domain.workforce_auto_planning.operational_demand import OperationalDemand
from app.domain.workforce_auto_planning.operational_demand_trace import (
    compute_operational_demand_trace_id,
)
from app.domain.workforce_auto_planning.proposed_shift_assignment import (
    ProposedShiftAssignment,
)
from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    WeeklyPlanningInputSnapshot,
)
from app.domain.workforce_auto_planning.weekly_proposal_composer import (
    ComposedWeeklyWorkforceProposal,
)


class LockedAssignmentPreservationError(ValueError):
    pass


class LockedAssignmentUnknownDemandTraceError(LockedAssignmentPreservationError):
    pass


class LockedAssignmentScopeMismatchError(LockedAssignmentPreservationError):
    pass


class LockedAssignmentDuplicateIdentityError(LockedAssignmentPreservationError):
    pass


class LockedAssignmentConflictStatus(str, Enum):
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"


class LockedAssignmentConflictReason(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class LockedAssignmentConflict(BaseModel):
    model_config = ConfigDict(frozen=True)

    workforce_member_id: str = Field(min_length=1)
    assignment_ids: tuple[str, str]
    operational_date: CalendarDate
    status: LockedAssignmentConflictStatus
    reason: LockedAssignmentConflictReason


class LockedDemandCoverage(BaseModel):
    model_config = ConfigDict(frozen=True)

    demand_trace_id: str = Field(min_length=1)
    locked_assignments_count: int = Field(ge=0, strict=True)
    target_quantity: int = Field(ge=0, strict=True)
    remaining_quantity: int = Field(ge=0, strict=True)
    overcoverage_quantity: int = Field(ge=0, strict=True)


class LockedAssignmentPreservationSet(BaseModel):
    model_config = ConfigDict(frozen=True)

    assignments: tuple[ProposedShiftAssignment, ...] = Field(default_factory=tuple)
    coverage_by_demand: tuple[LockedDemandCoverage, ...] = Field(
        default_factory=tuple
    )
    workforce_member_ids: tuple[str, ...] = Field(default_factory=tuple)
    demand_trace_ids: tuple[str, ...] = Field(default_factory=tuple)
    conflicts: tuple[LockedAssignmentConflict, ...] = Field(default_factory=tuple)


def _assignment_ordering_key(
    assignment: ProposedShiftAssignment,
) -> tuple[CalendarDate, str, str, str]:
    return (
        assignment.date,
        assignment.time_window.external_identifier,
        assignment.workforce_member_id,
        assignment.assignment_id,
    )


def _validate_locked_assignments(
    *,
    assignments: tuple[ProposedShiftAssignment, ...],
    snapshot: WeeklyPlanningInputSnapshot,
    demands_by_trace: dict[str, tuple[OperationalDemand, ...]],
) -> None:
    assignment_ids = tuple(item.assignment_id for item in assignments)
    if len(assignment_ids) != len(set(assignment_ids)):
        raise LockedAssignmentDuplicateIdentityError(
            "locked assignment identity must be unique"
        )

    for assignment in assignments:
        if len(demands_by_trace.get(assignment.demand_trace_id, ())) != 1:
            raise LockedAssignmentUnknownDemandTraceError(
                "locked assignment demand trace must resolve to exactly one demand"
            )
        if assignment.organization_id != snapshot.organization_id:
            raise LockedAssignmentScopeMismatchError(
                "locked assignment organization does not match snapshot"
            )
        if not snapshot.period_start <= assignment.date <= snapshot.period_end:
            raise LockedAssignmentScopeMismatchError(
                "locked assignment date falls outside snapshot period"
            )
        if (
            assignment.operational_unit.external_identifier
            != snapshot.operational_unit.external_identifier
        ):
            raise LockedAssignmentScopeMismatchError(
                "locked assignment operational unit does not match snapshot"
            )


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


def _conflict_for_pair(
    first: ProposedShiftAssignment,
    second: ProposedShiftAssignment,
) -> LockedAssignmentConflict | None:
    if (
        first.workforce_member_id != second.workforce_member_id
        or first.date != second.date
    ):
        return None
    assignment_ids = tuple(sorted((first.assignment_id, second.assignment_id)))
    first_window = _parse_time_window(first.time_window)
    second_window = _parse_time_window(second.time_window)
    if first_window is None or second_window is None:
        return LockedAssignmentConflict(
            workforce_member_id=first.workforce_member_id,
            assignment_ids=assignment_ids,
            operational_date=first.date,
            status=LockedAssignmentConflictStatus.UNKNOWN,
            reason=LockedAssignmentConflictReason(
                code="locked-time-window-uncertain",
                message=(
                    "At least one locked assignment time window cannot be "
                    "interpreted."
                ),
            ),
        )
    first_start, first_end = first_window
    second_start, second_end = second_window
    if first_start < second_end and second_start < first_end:
        return LockedAssignmentConflict(
            workforce_member_id=first.workforce_member_id,
            assignment_ids=assignment_ids,
            operational_date=first.date,
            status=LockedAssignmentConflictStatus.CONFLICT,
            reason=LockedAssignmentConflictReason(
                code="locked-time-window-overlap",
                message="Locked assignment time windows overlap.",
            ),
        )
    return None


def _conflicts(
    assignments: tuple[ProposedShiftAssignment, ...],
) -> tuple[LockedAssignmentConflict, ...]:
    values = tuple(
        conflict
        for index, first in enumerate(assignments)
        for second in assignments[index + 1 :]
        if (conflict := _conflict_for_pair(first, second)) is not None
    )
    return tuple(
        sorted(
            values,
            key=lambda item: (
                item.operational_date,
                item.workforce_member_id,
                item.assignment_ids,
                item.status.value,
            ),
        )
    )


def _coverage_by_demand(
    *,
    assignments: tuple[ProposedShiftAssignment, ...],
    demands_by_trace: dict[str, tuple[OperationalDemand, ...]],
) -> tuple[LockedDemandCoverage, ...]:
    counts: dict[str, int] = {}
    for assignment in assignments:
        counts[assignment.demand_trace_id] = (
            counts.get(assignment.demand_trace_id, 0) + 1
        )
    return tuple(
        LockedDemandCoverage(
            demand_trace_id=demand_trace_id,
            locked_assignments_count=locked_count,
            target_quantity=demands_by_trace[demand_trace_id][0].target_quantity,
            remaining_quantity=max(
                demands_by_trace[demand_trace_id][0].target_quantity
                - locked_count,
                0,
            ),
            overcoverage_quantity=max(
                locked_count
                - demands_by_trace[demand_trace_id][0].target_quantity,
                0,
            ),
        )
        for demand_trace_id, locked_count in sorted(counts.items())
    )


def build_locked_assignment_preservation_set(
    *,
    previous: ComposedWeeklyWorkforceProposal,
    snapshot: WeeklyPlanningInputSnapshot,
) -> LockedAssignmentPreservationSet:
    assignments = tuple(
        sorted(
            (
                assignment
                for assignment in previous.assignments
                if assignment.locked is True
            ),
            key=_assignment_ordering_key,
        )
    )
    demands_by_trace: dict[str, tuple[OperationalDemand, ...]] = {}
    for demand in snapshot.demands:
        demand_trace_id = compute_operational_demand_trace_id(demand)
        demands_by_trace[demand_trace_id] = (
            *demands_by_trace.get(demand_trace_id, ()),
            demand,
        )
    _validate_locked_assignments(
        assignments=assignments,
        snapshot=snapshot,
        demands_by_trace=demands_by_trace,
    )
    return LockedAssignmentPreservationSet(
        assignments=assignments,
        coverage_by_demand=_coverage_by_demand(
            assignments=assignments,
            demands_by_trace=demands_by_trace,
        ),
        workforce_member_ids=tuple(
            sorted({item.workforce_member_id for item in assignments})
        ),
        demand_trace_ids=tuple(
            sorted({item.demand_trace_id for item in assignments})
        ),
        conflicts=_conflicts(assignments),
    )
