from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters.amazon.operational_demand_converter import (
    AmazonPolicyMappingError,
    AmazonOperationalDemandInput,
    UnknownAmazonWorkloadError,
    convert_amazon_operational_demand,
)
from app.adapters.amazon.shift_time_window_policy import (
    AmazonShiftTimeWindowPolicyProvider,
)
from app.domain.core_language import OperationalUnit
from app.domain.workforce_auto_planning import (
    OperationalDemand,
    WorkloadCapabilityMapping,
)


def _input(workload_bucket: str, **overrides: object) -> AmazonOperationalDemandInput:
    values: dict[str, object] = {
        "organization_id": "organization-one",
        "operational_unit": OperationalUnit(
            external_identifier="DLO2",
            name="Primary station",
        ),
        "date": date(2026, 8, 24),
        "workload_bucket": workload_bucket,
        "base_quantity": 76,
        "source": "normalized-forecast",
    }
    values.update(overrides)
    return AmazonOperationalDemandInput.model_validate(values)


@pytest.mark.parametrize(
    ("workload_bucket", "expected_window", "expected_capability"),
    (
        (
            "NEXT_DAY",
            "amazon-next-day",
            "amazon-workload-next-day",
        ),
        (
            "SAME_DAY:A",
            "amazon-same-day-a",
            "amazon-workload-same-day-a",
        ),
        (
            "SAME_DAY:B_C",
            "amazon-same-day-b-c",
            "amazon-workload-same-day-b-c",
        ),
    ),
)
def test_supported_bucket_converts_through_c2_mapping(
    workload_bucket: str,
    expected_window: str,
    expected_capability: str,
) -> None:
    result = convert_amazon_operational_demand(
        _input(workload_bucket),
        AmazonShiftTimeWindowPolicyProvider(),
    )

    assert isinstance(result, OperationalDemand)
    assert result.capability_or_workload == expected_capability
    assert result.time_window.external_identifier == expected_window
    assert result.time_window.starts_at is None
    assert result.time_window.ends_at is None


def test_target_uses_configured_c1_buffer_and_half_up_rounding() -> None:
    result = convert_amazon_operational_demand(
        _input("NEXT_DAY"),
        AmazonShiftTimeWindowPolicyProvider(),
    )

    assert result.base_quantity == 76
    assert result.target_quantity == 84


def test_configured_buffer_changes_target_without_changing_converter() -> None:
    input_data = _input("NEXT_DAY", base_quantity=10)

    standard = convert_amazon_operational_demand(
        input_data,
        AmazonShiftTimeWindowPolicyProvider(),
    )
    configured = convert_amazon_operational_demand(
        input_data,
        AmazonShiftTimeWindowPolicyProvider(
            target_multiplier=Decimal("1.25")
        ),
    )

    assert standard.target_quantity == 11
    assert configured.target_quantity == 13


def test_unknown_bucket_is_rejected_without_fallback() -> None:
    with pytest.raises(
        UnknownAmazonWorkloadError,
        match="Unsupported Amazon workload bucket: UNKNOWN_BUCKET",
    ):
        convert_amazon_operational_demand(
            _input("UNKNOWN_BUCKET"),
            AmazonShiftTimeWindowPolicyProvider(),
        )


@pytest.mark.parametrize(
    "required_capabilities",
    ((), ("first-capability", "second-capability")),
)
def test_mapping_requires_exactly_one_capability(
    required_capabilities: tuple[str, ...],
) -> None:
    class InvalidCapabilityPolicy(AmazonShiftTimeWindowPolicyProvider):
        def workload_capability_mappings(
            self,
        ) -> tuple[WorkloadCapabilityMapping, ...]:
            return (
                WorkloadCapabilityMapping.model_construct(
                    workload_identifier="NEXT_DAY",
                    required_capabilities=required_capabilities,
                ),
            )

    with pytest.raises(
        AmazonPolicyMappingError,
        match=(
            "Amazon workload must resolve to exactly one capability: "
            "NEXT_DAY"
        ),
    ):
        convert_amazon_operational_demand(
            _input("NEXT_DAY"),
            InvalidCapabilityPolicy(),
        )


def test_identity_source_and_applied_policy_metadata_are_preserved() -> None:
    result = convert_amazon_operational_demand(
        _input(
            "SAME_DAY:A",
            organization_id="organization-two",
            source="normalized-source:42",
        ),
        AmazonShiftTimeWindowPolicyProvider(),
    )

    assert result.organization_id == "organization-two"
    assert result.source == "normalized-source:42"
    assert result.applied_policy is not None
    assert result.applied_policy.identifier == "amazon-operational-buffer"
    assert tuple(
        (item.key, item.value) for item in result.applied_policy.attributes
    ) == (
        ("target_multiplier", "1.10"),
        ("rounding", "ROUND_HALF_UP"),
    )


def test_conversion_is_side_effect_free_and_deterministic() -> None:
    input_data = _input("SAME_DAY:B_C")
    policy = AmazonShiftTimeWindowPolicyProvider()

    first = convert_amazon_operational_demand(input_data, policy)
    second = convert_amazon_operational_demand(input_data, policy)

    assert first == second
    assert input_data.base_quantity == 76
    assert policy.operational_buffer_policy().target_multiplier == Decimal(
        "1.10"
    )


def test_core_does_not_import_vertical_converter() -> None:
    core_directory = (
        Path(__file__).parents[1]
        / "app"
        / "domain"
        / "workforce_auto_planning"
    )

    for core_file in core_directory.glob("*.py"):
        source = core_file.read_text(encoding="utf-8").casefold()
        assert "app.adapters.amazon" not in source
        assert "app.plugins.dsp" not in source
