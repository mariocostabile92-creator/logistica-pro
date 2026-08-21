from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.core_language import OperationalUnit, TimeWindow
from app.domain.workforce_auto_planning import (
    AppliedPolicyMetadata,
    AssignedTimeSnapshot,
    AssignedTimeStatus,
    AssignedTimeUnit,
    CurrentMemberContractStateSnapshot,
    OperationalDemand,
    WeeklyHoursCapacityStatus,
    evaluate_weekly_hours_capacity,
)


def _demand(
    *,
    starts_at: str | None = "08:00",
    ends_at: str | None = "12:00",
) -> OperationalDemand:
    return OperationalDemand(
        organization_id="organization-one",
        operational_unit=OperationalUnit(external_identifier="unit-one"),
        date=date(2026, 8, 24),
        time_window=TimeWindow(
            external_identifier="window-one",
            starts_at=starts_at,
            ends_at=ends_at,
        ),
        capability_or_workload="opaque-capability",
        base_quantity=1,
        target_quantity=1,
        source="normalized-demand",
        applied_policy=AppliedPolicyMetadata(identifier="policy-one"),
    )


def _assigned(
    *,
    status: AssignedTimeStatus = AssignedTimeStatus.KNOWN,
    value: Decimal | None = Decimal("0"),
    unit: AssignedTimeUnit | None = AssignedTimeUnit.MINUTES,
) -> AssignedTimeSnapshot:
    return AssignedTimeSnapshot(status=status, value=value, unit=unit)


def _evaluate(
    *,
    weekly_hours: Decimal | None = Decimal("40"),
    assigned_time: AssignedTimeSnapshot | None = None,
    demand: OperationalDemand | None = None,
    employment_type: str | None = None,
    is_reserve: bool | None = None,
):
    return evaluate_weekly_hours_capacity(
        contract_state=CurrentMemberContractStateSnapshot(
            employment_type=employment_type,
            weekly_hours=weekly_hours,
            is_reserve=is_reserve,
        ),
        assigned_time=assigned_time or _assigned(),
        demand=demand or _demand(),
    )


def test_missing_weekly_hours_is_unknown_without_invented_capacity():
    result = _evaluate(weekly_hours=None)

    assert result.status == WeeklyHoursCapacityStatus.UNKNOWN
    assert result.contracted_weekly_minutes is None
    assert result.remaining_minutes is None
    assert result.reason.code == "weekly-hours-not-defined"


def test_unknown_assigned_time_is_unknown():
    result = _evaluate(
        assigned_time=_assigned(
            status=AssignedTimeStatus.UNKNOWN,
            value=None,
            unit=None,
        )
    )

    assert result.status == WeeklyHoursCapacityStatus.UNKNOWN
    assert result.already_assigned_minutes is None
    assert result.reason.code == "assigned-time-unknown"


def test_partial_assigned_time_is_unknown_without_optimistic_capacity():
    result = _evaluate(
        assigned_time=_assigned(
            status=AssignedTimeStatus.PARTIAL,
            value=Decimal("300"),
            unit=AssignedTimeUnit.MINUTES,
        )
    )

    assert result.status == WeeklyHoursCapacityStatus.UNKNOWN
    assert result.already_assigned_minutes is None
    assert result.remaining_minutes is None
    assert result.reason.code == "assigned-time-partial"


@pytest.mark.parametrize(
    "demand",
    (
        _demand(starts_at=None),
        _demand(ends_at=None),
        _demand(starts_at="12:00", ends_at="12:00"),
        _demand(starts_at="13:00", ends_at="12:00"),
    ),
)
def test_unsupported_demand_duration_is_unknown(demand):
    result = _evaluate(demand=demand)

    assert result.status == WeeklyHoursCapacityStatus.UNKNOWN
    assert result.requested_minutes is None
    assert result.reason.code == "demand-duration-unknown"


def test_contract_hours_are_converted_to_minutes_without_rounding():
    result = _evaluate(weekly_hours=Decimal("40"))
    fractional = _evaluate(weekly_hours=Decimal("37.5"))

    assert result.contracted_weekly_minutes == Decimal("2400")
    assert fractional.contracted_weekly_minutes == Decimal("2250.0")


def test_known_assigned_hours_are_converted_to_minutes():
    result = _evaluate(
        assigned_time=_assigned(
            value=Decimal("10.5"),
            unit=AssignedTimeUnit.HOURS,
        )
    )

    assert result.already_assigned_minutes == Decimal("630.0")


def test_known_assigned_minutes_are_used_directly():
    result = _evaluate(
        assigned_time=_assigned(
            value=Decimal("630"),
            unit=AssignedTimeUnit.MINUTES,
        )
    )

    assert result.already_assigned_minutes == Decimal("630")


def test_capacity_greater_than_requested_is_sufficient():
    result = _evaluate(
        assigned_time=_assigned(
            value=Decimal("1800"),
            unit=AssignedTimeUnit.MINUTES,
        )
    )

    assert result.status == WeeklyHoursCapacityStatus.SUFFICIENT
    assert result.requested_minutes == Decimal("240")
    assert result.remaining_minutes == Decimal("600")


def test_capacity_equal_to_requested_is_sufficient():
    result = _evaluate(
        assigned_time=_assigned(
            value=Decimal("2160"),
            unit=AssignedTimeUnit.MINUTES,
        )
    )

    assert result.status == WeeklyHoursCapacityStatus.SUFFICIENT
    assert result.requested_minutes == result.remaining_minutes == Decimal("240")


def test_requested_time_greater_than_remaining_is_insufficient():
    result = _evaluate(
        assigned_time=_assigned(
            value=Decimal("2220"),
            unit=AssignedTimeUnit.MINUTES,
        )
    )

    assert result.status == WeeklyHoursCapacityStatus.INSUFFICIENT
    assert result.requested_minutes == Decimal("240")
    assert result.remaining_minutes == Decimal("180")


def test_assigned_time_above_contract_is_insufficient_with_negative_remaining():
    result = _evaluate(
        assigned_time=_assigned(
            value=Decimal("2460"),
            unit=AssignedTimeUnit.MINUTES,
        )
    )

    assert result.status == WeeklyHoursCapacityStatus.INSUFFICIENT
    assert result.remaining_minutes == Decimal("-60")


@pytest.mark.parametrize(
    "contract_updates",
    (
        {"employment_type": "full-time"},
        {"employment_type": "part-time"},
        {"is_reserve": True},
        {"is_reserve": False},
    ),
)
def test_uninterpreted_contract_attributes_do_not_change_result(contract_updates):
    baseline = _evaluate()
    result = _evaluate(**contract_updates)

    assert result == baseline


def test_capability_and_workload_do_not_define_duration():
    demand = _demand(starts_at=None, ends_at=None)

    assert demand.capability_or_workload == "opaque-capability"
    assert _evaluate(demand=demand).status == WeeklyHoursCapacityStatus.UNKNOWN


def test_output_is_deterministic_and_immutable():
    first = _evaluate()
    second = _evaluate()

    assert first == second
    with pytest.raises(ValidationError):
        first.status = WeeklyHoursCapacityStatus.UNKNOWN
    with pytest.raises(ValidationError):
        first.reason.code = "changed"
    with pytest.raises(TypeError):
        first.evidence[0] = first.evidence[0]


def test_module_is_pure_neutral_and_not_integrated_into_evaluator():
    domain_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "domain"
        / "workforce_auto_planning"
    )
    source = (domain_path / "weekly_hours_capacity.py").read_text(
        encoding="utf-8"
    ).casefold()
    evaluator_source = (
        domain_path / "workforce_eligibility_evaluator.py"
    ).read_text(encoding="utf-8").casefold()

    forbidden_fragments = (
        "amazon",
        "dsp",
        "fleet",
        "vehicle",
        "repository",
        "sqlalchemy",
        "fastapi",
        "employment_type",
        "is_reserve",
        "contract_start",
        "contract_end",
        "shift_code",
        "overtime",
        "ranking",
        "scoring",
    )
    assert all(fragment not in source for fragment in forbidden_fragments)
    assert "evaluate_weekly_hours_capacity" not in evaluator_source
