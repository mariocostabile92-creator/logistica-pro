from datetime import date
from inspect import getsource

from app.domain.core_language import OperationalUnit, TimeWindow
from app.domain.workforce_auto_planning import (
    AppliedPolicyAttribute,
    AppliedPolicyMetadata,
    OperationalDemand,
    compute_operational_demand_trace_id,
)
from app.domain.workforce_auto_planning import (
    operational_demand_trace as trace_module,
)


def _demand(**overrides: object) -> OperationalDemand:
    values: dict[str, object] = {
        "organization_id": "organization-one",
        "operational_unit": OperationalUnit(
            external_identifier="unit-north",
            name="North depot",
        ),
        "date": date(2026, 8, 24),
        "time_window": TimeWindow(
            external_identifier="morning-window",
            starts_at="08:00",
            ends_at="16:00",
        ),
        "capability_or_workload": "parcel-delivery",
        "base_quantity": 8,
        "target_quantity": 9,
        "source": "weekly-forecast",
        "applied_policy": None,
    }
    values.update(overrides)
    return OperationalDemand.model_validate(values)


def test_same_logical_demand_produces_the_same_trace_id() -> None:
    demand = _demand()

    assert compute_operational_demand_trace_id(demand) == (
        compute_operational_demand_trace_id(demand)
    )


def test_distinct_instances_with_same_identity_produce_the_same_trace_id() -> None:
    assert compute_operational_demand_trace_id(_demand()) == (
        compute_operational_demand_trace_id(_demand())
    )


def test_each_identity_field_changes_the_trace_id() -> None:
    original = _demand()
    original_trace = compute_operational_demand_trace_id(original)
    changed_demands = (
        _demand(organization_id="organization-two"),
        _demand(
            operational_unit=OperationalUnit(
                external_identifier="unit-south",
                name="South depot",
            )
        ),
        _demand(date=date(2026, 8, 25)),
        _demand(
            time_window=TimeWindow(
                external_identifier="afternoon-window",
                starts_at="12:00",
                ends_at="20:00",
            )
        ),
        _demand(capability_or_workload="returns"),
        _demand(source="manual-requirement"),
    )

    assert all(
        compute_operational_demand_trace_id(changed) != original_trace
        for changed in changed_demands
    )


def test_quantities_do_not_change_the_trace_id() -> None:
    original_trace = compute_operational_demand_trace_id(_demand())

    assert compute_operational_demand_trace_id(
        _demand(base_quantity=12)
    ) == original_trace
    assert compute_operational_demand_trace_id(
        _demand(target_quantity=14)
    ) == original_trace


def test_applied_policy_does_not_change_the_trace_id() -> None:
    policy = AppliedPolicyMetadata(
        identifier="capacity-policy",
        version="2",
        attributes=(AppliedPolicyAttribute(key="mode", value="strict"),),
    )

    assert compute_operational_demand_trace_id(_demand()) == (
        compute_operational_demand_trace_id(_demand(applied_policy=policy))
    )


def test_time_window_definition_does_not_change_the_isolated_trace_id() -> None:
    changed_definition = TimeWindow(
        external_identifier="morning-window",
        starts_at="09:00",
        ends_at="17:00",
    )

    assert compute_operational_demand_trace_id(_demand()) == (
        compute_operational_demand_trace_id(
            _demand(time_window=changed_definition)
        )
    )


def test_operational_unit_name_does_not_change_the_trace_id() -> None:
    renamed_unit = OperationalUnit(
        external_identifier="unit-north",
        name="Renamed depot",
    )

    assert compute_operational_demand_trace_id(_demand()) == (
        compute_operational_demand_trace_id(
            _demand(operational_unit=renamed_unit)
        )
    )


def test_trace_id_is_lowercase_sha256_hex() -> None:
    trace_id = compute_operational_demand_trace_id(_demand())

    assert len(trace_id) == 64
    assert trace_id == trace_id.lower()
    assert all(character in "0123456789abcdef" for character in trace_id)


def test_trace_implementation_has_no_random_runtime_identity() -> None:
    source = getsource(trace_module).casefold()

    assert "random" not in source
    assert "uuid" not in source
    assert "timestamp" not in source
