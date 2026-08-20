from decimal import Decimal
from pathlib import Path

from app.adapters.amazon.shift_time_window_policy import (
    AmazonShiftTimeWindowPolicyProvider,
)
from app.domain.core_language import TimeWindow
from app.domain.workforce_auto_planning import (
    ShiftCatalogueEntry,
    WorkforcePlanningPolicyProvider,
    WorkloadCapabilityMapping,
)


def _provider() -> AmazonShiftTimeWindowPolicyProvider:
    return AmazonShiftTimeWindowPolicyProvider()


def test_all_supported_vertical_buckets_and_shift_codes_are_represented() -> None:
    provider = _provider()

    shifts = provider.shift_catalogue()
    mappings = provider.workload_capability_mappings()

    assert tuple(item.identifier for item in shifts) == (
        "C1",
        "L1",
        "L2",
        "L3",
        "VMC1",
        "SA",
        "SB",
    )
    assert tuple(item.workload_identifier for item in mappings) == (
        "NEXT_DAY",
        "SAME_DAY:A",
        "SAME_DAY:B_C",
    )


def test_shift_codes_map_to_their_supported_named_windows() -> None:
    shifts = {item.identifier: item for item in _provider().shift_catalogue()}

    assert {
        shifts[code].time_window_identifier
        for code in ("C1", "L1", "L2", "L3", "VMC1")
    } == {"amazon-next-day"}
    assert shifts["SA"].time_window_identifier == "amazon-same-day-a"
    assert shifts["SB"].time_window_identifier == "amazon-same-day-b-c"


def test_workloads_and_shifts_share_neutral_capability_keys() -> None:
    provider = _provider()
    shifts = {item.identifier: item for item in provider.shift_catalogue()}
    mappings = {
        item.workload_identifier: item
        for item in provider.workload_capability_mappings()
    }

    assert shifts["C1"].required_capabilities == mappings[
        "NEXT_DAY"
    ].required_capabilities
    assert shifts["SA"].required_capabilities == mappings[
        "SAME_DAY:A"
    ].required_capabilities
    assert shifts["SB"].required_capabilities == mappings[
        "SAME_DAY:B_C"
    ].required_capabilities


def test_named_windows_do_not_invent_clock_boundaries() -> None:
    windows = _provider().time_windows()

    assert tuple(item.external_identifier for item in windows) == (
        "amazon-next-day",
        "amazon-same-day-a",
        "amazon-same-day-b-c",
    )
    assert all(item.starts_at is None for item in windows)
    assert all(item.ends_at is None for item in windows)


def test_mapping_returns_only_neutral_core_value_objects() -> None:
    provider = _provider()

    assert isinstance(provider, WorkforcePlanningPolicyProvider)
    assert all(
        isinstance(item, ShiftCatalogueEntry)
        for item in provider.shift_catalogue()
    )
    assert all(isinstance(item, TimeWindow) for item in provider.time_windows())
    assert all(
        isinstance(item, WorkloadCapabilityMapping)
        for item in provider.workload_capability_mappings()
    )


def test_mapping_and_inherited_buffer_are_deterministic_and_configurable() -> None:
    first = AmazonShiftTimeWindowPolicyProvider(
        target_multiplier=Decimal("1.16")
    )
    second = AmazonShiftTimeWindowPolicyProvider(
        target_multiplier=Decimal("1.16")
    )

    assert first.shift_catalogue() == second.shift_catalogue()
    assert first.time_windows() == second.time_windows()
    assert (
        first.workload_capability_mappings()
        == second.workload_capability_mappings()
    )
    assert first.operational_buffer_policy().target_multiplier == Decimal(
        "1.16"
    )


def test_core_has_no_vertical_imports_or_vocabulary() -> None:
    core_directory = (
        Path(__file__).parents[1]
        / "app"
        / "domain"
        / "workforce_auto_planning"
    )
    forbidden_terms = (
        "amazon",
        "dsp",
        "next_day",
        "same_day",
        "vmc1",
    )

    for core_file in core_directory.glob("*.py"):
        source = core_file.read_text(encoding="utf-8").casefold()
        assert all(term not in source for term in forbidden_terms)
