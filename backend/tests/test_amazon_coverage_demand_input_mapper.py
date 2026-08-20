import json
from pathlib import Path

import pytest

from app.adapters.amazon.coverage_operational_demand_input_mapper import (
    AMAZON_COVERAGE_DEMAND_SOURCE_CONTEXT,
    AmazonCoverageDemandBindingError,
    UnknownAmazonCoverageDemandBucketError,
    map_coverage_demand_to_amazon_input,
)
from app.adapters.amazon.operational_demand_converter import (
    AmazonOperationalDemandInput,
    convert_amazon_operational_demand,
)
from app.adapters.amazon.shift_time_window_policy import (
    AmazonShiftTimeWindowPolicyProvider,
)
from app.domain.core_language import OperationalUnit
from app.domain.workforce_auto_planning import (
    PlanningOperationalUnitBinding,
)
from app.plugins.workforce.domain.coverage import (
    EffectiveCoverageDemandRow,
    ForecastAuthorityStatus,
)


def _row(**overrides: object) -> EffectiveCoverageDemandRow:
    values: dict[str, object] = {
        "organization_id": "organization-one",
        "operational_date": "2026-08-24",
        "cycle": "NEXT_DAY",
        "segment": None,
        "station": None,
        "forecast_routes": 76,
        "source": "IMPORT",
        "source_identity": "forecast-import:2026-08-24",
        "authority_status": ForecastAuthorityStatus.AUTHORITATIVE,
        "detection_reason": None,
    }
    values.update(overrides)
    return EffectiveCoverageDemandRow.model_validate(values)


def _binding(**overrides: object) -> PlanningOperationalUnitBinding:
    values: dict[str, object] = {
        "organization_id": "organization-one",
        "demand_source_context": AMAZON_COVERAGE_DEMAND_SOURCE_CONTEXT,
        "operational_unit": OperationalUnit(
            external_identifier="DLO2",
            name="Primary station",
        ),
        "binding_version": 1,
        "active": True,
    }
    values.update(overrides)
    return PlanningOperationalUnitBinding.model_validate(values)


@pytest.mark.parametrize(
    ("cycle", "segment", "expected_bucket"),
    (
        ("NEXT_DAY", None, "NEXT_DAY"),
        ("SAME_DAY", "A", "SAME_DAY:A"),
        ("SAME_DAY", "B_C", "SAME_DAY:B_C"),
    ),
)
def test_supported_coverage_bucket_is_mapped_exactly(
    cycle: str,
    segment: str | None,
    expected_bucket: str,
):
    result = map_coverage_demand_to_amazon_input(
        _row(cycle=cycle, segment=segment),
        _binding(),
    )

    assert result.workload_bucket == expected_bucket


def test_raw_forecast_becomes_base_quantity_without_buffer():
    result = map_coverage_demand_to_amazon_input(_row(), _binding())

    assert result.base_quantity == 76
    assert not hasattr(result, "target_quantity")


def test_organization_mismatch_is_rejected():
    with pytest.raises(
        AmazonCoverageDemandBindingError,
        match="organizations do not match",
    ):
        map_coverage_demand_to_amazon_input(
            _row(organization_id="organization-one"),
            _binding(organization_id="organization-two"),
        )


def test_inactive_binding_is_rejected():
    with pytest.raises(AmazonCoverageDemandBindingError, match="inactive"):
        map_coverage_demand_to_amazon_input(_row(), _binding(active=False))


def test_binding_context_mismatch_is_rejected():
    with pytest.raises(
        AmazonCoverageDemandBindingError,
        match="context is not supported",
    ):
        map_coverage_demand_to_amazon_input(
            _row(),
            _binding(demand_source_context="another-context"),
        )


def test_station_none_uses_only_the_explicit_binding():
    result = map_coverage_demand_to_amazon_input(
        _row(station=None),
        _binding(),
    )

    assert result.operational_unit == _binding().operational_unit
    assert result.operational_unit.external_identifier == "DLO2"


def test_exactly_matching_station_is_accepted():
    result = map_coverage_demand_to_amazon_input(
        _row(station="DLO2"),
        _binding(),
    )

    assert result.operational_unit.external_identifier == "DLO2"


def test_station_comparison_does_not_add_normalization():
    with pytest.raises(
        AmazonCoverageDemandBindingError,
        match="does not match",
    ):
        map_coverage_demand_to_amazon_input(
            _row(station="dlo2"),
            _binding(),
        )


@pytest.mark.parametrize(
    ("cycle", "segment"),
    (
        ("UNKNOWN", None),
        ("NEXT_DAY", "A"),
        ("SAME_DAY", None),
        ("SAME_DAY", "C"),
    ),
)
def test_unknown_cycle_segment_is_rejected(cycle, segment):
    with pytest.raises(UnknownAmazonCoverageDemandBucketError):
        map_coverage_demand_to_amazon_input(
            _row(cycle=cycle, segment=segment),
            _binding(),
        )


def test_provenance_is_canonical_and_deterministic():
    row = _row(
        authority_status=ForecastAuthorityStatus.SUSPECT_TEMPLATE,
        detection_reason="CORRELATED_CONSTANT_BLOCK",
    )

    first = map_coverage_demand_to_amazon_input(row, _binding())
    second = map_coverage_demand_to_amazon_input(row, _binding())

    assert first.source == second.source
    assert first.source.startswith("coverage:")
    assert json.loads(first.source.removeprefix("coverage:")) == {
        "authority_status": "SUSPECT_TEMPLATE",
        "detection_reason": "CORRELATED_CONSTANT_BLOCK",
        "source": "IMPORT",
        "source_identity": "forecast-import:2026-08-24",
    }


def test_volatile_or_unrelated_metadata_does_not_enter_provenance():
    row = _row()
    augmented = row.model_copy(
        update={
            "coverage_requirement_id": 999,
            "updated_at": "2099-01-01T00:00:00Z",
            "source_reference": "Workbook!Z999",
        }
    )

    original = map_coverage_demand_to_amazon_input(row, _binding())
    result = map_coverage_demand_to_amazon_input(augmented, _binding())

    assert result.source == original.source
    assert "2099" not in result.source
    assert "Workbook" not in result.source


def test_same_input_produces_the_same_immutable_output():
    row = _row()
    binding = _binding()

    first = map_coverage_demand_to_amazon_input(row, binding)
    second = map_coverage_demand_to_amazon_input(row, binding)

    assert isinstance(first, AmazonOperationalDemandInput)
    assert first == second
    assert row.forecast_routes == 76
    assert binding.active is True


def test_c3_consumes_mapper_output_and_applies_buffer_later():
    mapped = map_coverage_demand_to_amazon_input(_row(), _binding())

    demand = convert_amazon_operational_demand(
        mapped,
        AmazonShiftTimeWindowPolicyProvider(),
    )

    assert mapped.base_quantity == 76
    assert demand.base_quantity == 76
    assert demand.target_quantity == 84
    assert demand.operational_unit.external_identifier == "DLO2"


def test_mapper_has_no_runtime_or_persistence_access():
    mapper_file = (
        Path(__file__).parents[1]
        / "app"
        / "adapters"
        / "amazon"
        / "coverage_operational_demand_input_mapper.py"
    )
    source = mapper_file.read_text(encoding="utf-8").casefold()

    forbidden = (
        "repository",
        "configuration engine",
        "db_session",
        "current_organization_id",
        "required_capacity_for",
        "assigned_driver",
        "datetime.now",
        "uuid",
    )
    assert all(item not in source for item in forbidden)
