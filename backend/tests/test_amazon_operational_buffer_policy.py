from decimal import Decimal
from pathlib import Path

from app.adapters.amazon.operational_buffer_policy import (
    AmazonOperationalBufferPolicyProvider,
)
from app.domain.workforce_auto_planning import (
    OperationalBufferPolicy,
    WorkforcePlanningPolicyProvider,
)


def test_default_policy_exposes_ten_percent_operational_buffer() -> None:
    provider = AmazonOperationalBufferPolicyProvider()

    policy = provider.operational_buffer_policy()

    assert isinstance(policy, OperationalBufferPolicy)
    assert policy.target_multiplier == Decimal("1.10")


def test_policy_implements_neutral_provider_contract() -> None:
    provider = AmazonOperationalBufferPolicyProvider()

    assert isinstance(provider, WorkforcePlanningPolicyProvider)
    assert provider.operational_buffer_policy().identifier == (
        "amazon-operational-buffer"
    )


def test_buffer_is_configurable_without_changing_core_contract() -> None:
    provider = AmazonOperationalBufferPolicyProvider(
        target_multiplier=Decimal("1.18")
    )

    assert provider.operational_buffer_policy().target_multiplier == Decimal(
        "1.18"
    )


def test_out_of_scope_policy_sections_are_empty_and_deterministic() -> None:
    provider = AmazonOperationalBufferPolicyProvider()

    assert provider.shift_catalogue() == ()
    assert provider.time_windows() == ()
    assert provider.workload_capability_mappings() == ()
    assert provider.priorities_and_preferences() == ()
    assert provider.additional_rules() == ()


def test_core_does_not_import_vertical_adapter() -> None:
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
