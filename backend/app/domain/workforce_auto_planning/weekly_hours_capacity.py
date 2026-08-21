from datetime import time
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.domain.workforce_auto_planning.constraint_evaluation import (
    ConstraintEvidence,
)
from app.domain.workforce_auto_planning.operational_demand import (
    OperationalDemand,
)
from app.domain.workforce_auto_planning.weekly_planning_input_snapshot import (
    AssignedTimeSnapshot,
    AssignedTimeStatus,
    AssignedTimeUnit,
    CurrentMemberContractStateSnapshot,
)
from app.domain.workforce_auto_planning.workforce_eligibility_decision import (
    EligibilityDecisionNotice,
)


class WeeklyHoursCapacityStatus(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"
    UNKNOWN = "UNKNOWN"


class WeeklyHoursCapacityEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: WeeklyHoursCapacityStatus
    contracted_weekly_minutes: Decimal | None = Field(default=None, ge=0)
    already_assigned_minutes: Decimal | None = Field(default=None, ge=0)
    requested_minutes: Decimal | None = Field(default=None, ge=0)
    remaining_minutes: Decimal | None = None
    reason: EligibilityDecisionNotice
    evidence: tuple[ConstraintEvidence, ...] = Field(default_factory=tuple)


def _decimal_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _assigned_minutes(assigned_time: AssignedTimeSnapshot) -> Decimal | None:
    if assigned_time.status != AssignedTimeStatus.KNOWN:
        return None
    if assigned_time.unit == AssignedTimeUnit.HOURS:
        return assigned_time.value * Decimal("60")
    if assigned_time.unit == AssignedTimeUnit.MINUTES:
        return assigned_time.value
    return None


def _time_microseconds(value: time) -> int:
    return (
        ((value.hour * 60 + value.minute) * 60 + value.second) * 1_000_000
        + value.microsecond
    )


def _requested_minutes(demand: OperationalDemand) -> Decimal | None:
    starts_at = demand.time_window.starts_at
    ends_at = demand.time_window.ends_at
    if starts_at is None or ends_at is None:
        return None
    try:
        start = time.fromisoformat(starts_at)
        end = time.fromisoformat(ends_at)
    except ValueError:
        return None
    if start.tzinfo is not None or end.tzinfo is not None or end <= start:
        return None
    elapsed_microseconds = _time_microseconds(end) - _time_microseconds(start)
    return Decimal(elapsed_microseconds) / Decimal("60000000")


def _evidence(
    *,
    contract_state: CurrentMemberContractStateSnapshot,
    assigned_time: AssignedTimeSnapshot,
    demand: OperationalDemand,
    contracted_weekly_minutes: Decimal | None,
    already_assigned_minutes: Decimal | None,
    requested_minutes: Decimal | None,
    remaining_minutes: Decimal | None,
) -> tuple[ConstraintEvidence, ...]:
    return (
        ConstraintEvidence(
            key="weekly-hours-original",
            value=_decimal_text(contract_state.weekly_hours),
        ),
        ConstraintEvidence(
            key="assigned-time-status",
            value=assigned_time.status.value,
        ),
        ConstraintEvidence(
            key="assigned-time-value",
            value=_decimal_text(assigned_time.value),
        ),
        ConstraintEvidence(
            key="assigned-time-unit",
            value=(
                assigned_time.unit.value
                if assigned_time.unit is not None
                else None
            ),
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
            key="contracted-weekly-minutes",
            value=_decimal_text(contracted_weekly_minutes),
        ),
        ConstraintEvidence(
            key="already-assigned-minutes",
            value=_decimal_text(already_assigned_minutes),
        ),
        ConstraintEvidence(
            key="requested-minutes",
            value=_decimal_text(requested_minutes),
        ),
        ConstraintEvidence(
            key="remaining-minutes",
            value=_decimal_text(remaining_minutes),
        ),
    )


def _result(
    *,
    status: WeeklyHoursCapacityStatus,
    contracted_weekly_minutes: Decimal | None,
    already_assigned_minutes: Decimal | None,
    requested_minutes: Decimal | None,
    remaining_minutes: Decimal | None,
    reason_code: str,
    reason_message: str,
    evidence: tuple[ConstraintEvidence, ...],
) -> WeeklyHoursCapacityEvaluation:
    return WeeklyHoursCapacityEvaluation(
        status=status,
        contracted_weekly_minutes=contracted_weekly_minutes,
        already_assigned_minutes=already_assigned_minutes,
        requested_minutes=requested_minutes,
        remaining_minutes=remaining_minutes,
        reason=EligibilityDecisionNotice(
            code=reason_code,
            message=reason_message,
        ),
        evidence=evidence,
    )


def evaluate_weekly_hours_capacity(
    *,
    contract_state: CurrentMemberContractStateSnapshot,
    assigned_time: AssignedTimeSnapshot,
    demand: OperationalDemand,
) -> WeeklyHoursCapacityEvaluation:
    contracted_weekly_minutes = (
        contract_state.weekly_hours * Decimal("60")
        if contract_state.weekly_hours is not None
        else None
    )
    already_assigned_minutes = _assigned_minutes(assigned_time)
    requested_minutes = _requested_minutes(demand)
    remaining_minutes = (
        contracted_weekly_minutes - already_assigned_minutes
        if contracted_weekly_minutes is not None
        and already_assigned_minutes is not None
        else None
    )
    evidence = _evidence(
        contract_state=contract_state,
        assigned_time=assigned_time,
        demand=demand,
        contracted_weekly_minutes=contracted_weekly_minutes,
        already_assigned_minutes=already_assigned_minutes,
        requested_minutes=requested_minutes,
        remaining_minutes=remaining_minutes,
    )

    if contracted_weekly_minutes is None:
        return _result(
            status=WeeklyHoursCapacityStatus.UNKNOWN,
            contracted_weekly_minutes=None,
            already_assigned_minutes=already_assigned_minutes,
            requested_minutes=requested_minutes,
            remaining_minutes=None,
            reason_code="weekly-hours-not-defined",
            reason_message="Contracted weekly hours are not defined.",
            evidence=evidence,
        )
    if assigned_time.status == AssignedTimeStatus.PARTIAL:
        return _result(
            status=WeeklyHoursCapacityStatus.UNKNOWN,
            contracted_weekly_minutes=contracted_weekly_minutes,
            already_assigned_minutes=None,
            requested_minutes=requested_minutes,
            remaining_minutes=None,
            reason_code="assigned-time-partial",
            reason_message="Assigned time is only partially known.",
            evidence=evidence,
        )
    if already_assigned_minutes is None:
        return _result(
            status=WeeklyHoursCapacityStatus.UNKNOWN,
            contracted_weekly_minutes=contracted_weekly_minutes,
            already_assigned_minutes=None,
            requested_minutes=requested_minutes,
            remaining_minutes=None,
            reason_code="assigned-time-unknown",
            reason_message="Assigned time is not authoritatively known.",
            evidence=evidence,
        )
    if requested_minutes is None:
        return _result(
            status=WeeklyHoursCapacityStatus.UNKNOWN,
            contracted_weekly_minutes=contracted_weekly_minutes,
            already_assigned_minutes=already_assigned_minutes,
            requested_minutes=None,
            remaining_minutes=remaining_minutes,
            reason_code="demand-duration-unknown",
            reason_message="Demand duration cannot be determined.",
            evidence=evidence,
        )

    sufficient = requested_minutes <= remaining_minutes
    return _result(
        status=(
            WeeklyHoursCapacityStatus.SUFFICIENT
            if sufficient
            else WeeklyHoursCapacityStatus.INSUFFICIENT
        ),
        contracted_weekly_minutes=contracted_weekly_minutes,
        already_assigned_minutes=already_assigned_minutes,
        requested_minutes=requested_minutes,
        remaining_minutes=remaining_minutes,
        reason_code=(
            "weekly-hours-capacity-sufficient"
            if sufficient
            else "weekly-hours-capacity-insufficient"
        ),
        reason_message=(
            "Remaining weekly capacity covers the demand duration."
            if sufficient
            else "Remaining weekly capacity does not cover the demand duration."
        ),
        evidence=evidence,
    )
