from decimal import Decimal
from inspect import getsource
import re
from typing import get_type_hints

import pytest
from pydantic import ValidationError

from app.domain.core_language import TimeWindow
from app.domain.workforce_auto_planning import (
    OperationalBufferPolicy,
    PlanningPriorityOrPreference,
    PlanningRuleDescriptor,
    PlanningRuleParameter,
    ShiftCatalogueEntry,
    WorkforcePlanningPolicyProvider,
    WorkloadCapabilityMapping,
)
from app.domain.workforce_auto_planning import planning_policy as policy_module


class GenericPlanningPolicy:
    def __init__(self, target_multiplier: Decimal) -> None:
        self._target_multiplier = target_multiplier

    def operational_buffer_policy(self) -> OperationalBufferPolicy:
        return OperationalBufferPolicy(
            identifier="service-reserve",
            target_multiplier=self._target_multiplier,
        )

    def shift_catalogue(self) -> tuple[ShiftCatalogueEntry, ...]:
        return (
            ShiftCatalogueEntry(
                identifier="early-shift",
                label="Early shift",
                time_window_identifier="early-window",
                required_capabilities=("parcel-delivery",),
            ),
        )

    def time_windows(self) -> tuple[TimeWindow, ...]:
        return (
            TimeWindow(
                external_identifier="early-window",
                starts_at="06:00",
                ends_at="14:00",
            ),
        )

    def workload_capability_mappings(
        self,
    ) -> tuple[WorkloadCapabilityMapping, ...]:
        return (
            WorkloadCapabilityMapping(
                workload_identifier="parcel-delivery",
                required_capabilities=("commercial-driving",),
            ),
        )

    def priorities_and_preferences(
        self,
    ) -> tuple[PlanningPriorityOrPreference, ...]:
        return (
            PlanningPriorityOrPreference(
                identifier="continuity",
                priority=20,
                preference="same-operational-unit",
            ),
        )

    def additional_rules(self) -> tuple[PlanningRuleDescriptor, ...]:
        return (
            PlanningRuleDescriptor(
                identifier="customer-defined-rule",
                parameters=(
                    PlanningRuleParameter(key="threshold", value=3),
                ),
            ),
        )


def test_generic_policy_structurally_implements_provider_contract() -> None:
    provider = GenericPlanningPolicy(Decimal("1.05"))

    assert isinstance(provider, WorkforcePlanningPolicyProvider)
    assert provider.operational_buffer_policy().identifier == "service-reserve"


def test_two_providers_can_supply_different_buffer_configurations() -> None:
    standard = GenericPlanningPolicy(Decimal("1.05"))
    peak = GenericPlanningPolicy(Decimal("1.25"))

    assert (
        standard.operational_buffer_policy().target_multiplier
        != peak.operational_buffer_policy().target_multiplier
    )


def test_provider_describes_neutral_planning_inputs() -> None:
    provider = GenericPlanningPolicy(Decimal("1.05"))

    assert provider.shift_catalogue()[0].identifier == "early-shift"
    assert provider.time_windows()[0].external_identifier == "early-window"
    assert (
        provider.workload_capability_mappings()[0].required_capabilities
        == ("commercial-driving",)
    )
    assert provider.priorities_and_preferences()[0].priority == 20
    assert provider.additional_rules()[0].parameters[0].value == 3


def test_core_policy_contract_has_no_vertical_specific_terminology() -> None:
    source = getsource(policy_module).casefold()
    forbidden_terms = (
        "amazon",
        "dsp",
        "next_day",
        "same_day",
        "vmc1",
        "+10%",
    )

    assert all(term not in source for term in forbidden_terms)
    assert re.search(r"\b(c1|l1|l2|l3|sa|sb)\b", source) is None


def test_protocol_imports_and_return_types_are_deterministic() -> None:
    hints = get_type_hints(WorkforcePlanningPolicyProvider.shift_catalogue)

    assert hints["return"] == tuple[ShiftCatalogueEntry, ...]


def test_policy_value_objects_are_validated_and_immutable() -> None:
    policy = OperationalBufferPolicy(
        identifier="service-reserve",
        target_multiplier=Decimal("1.05"),
    )

    with pytest.raises(ValidationError):
        OperationalBufferPolicy(identifier="", target_multiplier=Decimal("1"))
    with pytest.raises(ValidationError):
        OperationalBufferPolicy(
            identifier="invalid",
            target_multiplier=Decimal("0"),
        )
    with pytest.raises(ValidationError):
        policy.target_multiplier = Decimal("2")
