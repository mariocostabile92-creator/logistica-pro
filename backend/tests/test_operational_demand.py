from datetime import date
from inspect import getsource

import pytest
from pydantic import ValidationError

from app.domain.core_language import OperationalUnit, TimeWindow
from app.domain.workforce_auto_planning import (
    AppliedPolicyAttribute,
    AppliedPolicyMetadata,
    OperationalDemand,
)
from app.domain.workforce_auto_planning import operational_demand as demand_module


def _generic_demand(**overrides: object) -> OperationalDemand:
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
            ends_at="12:00",
        ),
        "capability_or_workload": "temperature-controlled-delivery",
        "base_quantity": 12,
        "target_quantity": 12,
        "source": "customer-forecast",
        "applied_policy": None,
    }
    values.update(overrides)
    return OperationalDemand.model_validate(values)


def test_represents_a_generic_operational_demand() -> None:
    demand = _generic_demand(
        applied_policy=AppliedPolicyMetadata(
            identifier="customer-defined-adjustment",
            version="v1",
            attributes=(
                AppliedPolicyAttribute(key="service_level", value="priority"),
            ),
        )
    )

    assert demand.operational_unit.external_identifier == "unit-north"
    assert demand.time_window.external_identifier == "morning-window"
    assert demand.capability_or_workload == "temperature-controlled-delivery"
    assert demand.applied_policy is not None
    assert demand.applied_policy.attributes[0].key == "service_level"


def test_base_and_target_can_differ_without_an_assumed_reason() -> None:
    demand = _generic_demand(base_quantity=12, target_quantity=15)

    assert demand.base_quantity == 12
    assert demand.target_quantity == 15
    assert demand.applied_policy is None


def test_organization_identity_keeps_demands_logically_separate() -> None:
    first = _generic_demand(organization_id="organization-one")
    second = _generic_demand(organization_id="organization-two")

    assert first.organization_id != second.organization_id
    assert first != second


def test_contract_contains_no_vertical_specific_terminology() -> None:
    source = getsource(demand_module).casefold()
    forbidden_terms = (
        "amazon",
        "dsp",
        "next_day",
        "same_day",
        "+10%",
    )

    assert all(term not in source for term in forbidden_terms)


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    (
        ("organization_id", ""),
        ("operational_unit", {"external_identifier": ""}),
        ("time_window", {"external_identifier": ""}),
        ("capability_or_workload", ""),
        ("base_quantity", -1),
        ("target_quantity", -1),
        ("source", ""),
        ("applied_policy", {"identifier": ""}),
    ),
)
def test_invalid_essential_inputs_are_rejected_deterministically(
    field: str,
    invalid_value: object,
) -> None:
    with pytest.raises(ValidationError):
        _generic_demand(**{field: invalid_value})


def test_contract_and_nested_metadata_are_immutable() -> None:
    demand = _generic_demand(
        applied_policy=AppliedPolicyMetadata(
            identifier="customer-defined-adjustment",
            attributes=(AppliedPolicyAttribute(key="priority", value=2),),
        )
    )

    with pytest.raises(ValidationError):
        demand.target_quantity = 16

    assert demand.applied_policy is not None
    with pytest.raises(ValidationError):
        demand.applied_policy.identifier = "changed"
