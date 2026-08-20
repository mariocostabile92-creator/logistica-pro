from datetime import date
from pathlib import Path

import pytest

from app.adapters.amazon.coverage_operational_demand_input_mapper import (
    AMAZON_COVERAGE_DEMAND_SOURCE_CONTEXT,
    AmazonCoverageDemandBindingError,
    AmazonCoverageDemandInputMappingError,
    map_coverage_demand_to_amazon_input,
)
from app.adapters.amazon.operational_demand_converter import (
    AmazonOperationalDemandInput,
    convert_amazon_operational_demand,
)
from app.adapters.amazon.operational_demand_provider import (
    AmazonOperationalDemandProviderAdapter,
    AmazonOperationalDemandProviderValidationError,
)
from app.adapters.amazon.shift_time_window_policy import (
    AmazonShiftTimeWindowPolicyProvider,
)
from app.domain.core_language import OperationalUnit, TimeWindow
from app.domain.workforce_auto_planning import (
    AppliedPolicyMetadata,
    OperationalDemand,
    OperationalDemandProvider,
    PlanningOperationalUnitBinding,
)
from app.plugins.workforce.domain.coverage import (
    EffectiveCoverageDemandRow,
    ForecastAuthorityStatus,
)


ORG = "organization-one"
UNIT = OperationalUnit(external_identifier="DLO2", name="Primary station")
START = date(2026, 8, 24)
END = date(2026, 8, 30)


def _row(**overrides: object) -> EffectiveCoverageDemandRow:
    values: dict[str, object] = {
        "organization_id": ORG,
        "operational_date": "2026-08-24",
        "cycle": "NEXT_DAY",
        "segment": None,
        "station": None,
        "forecast_routes": 76,
        "source": "IMPORT",
        "source_identity": "forecast-import:next-day",
        "authority_status": ForecastAuthorityStatus.AUTHORITATIVE,
        "detection_reason": None,
    }
    values.update(overrides)
    return EffectiveCoverageDemandRow.model_validate(values)


def _binding(**overrides: object) -> PlanningOperationalUnitBinding:
    values: dict[str, object] = {
        "organization_id": ORG,
        "demand_source_context": AMAZON_COVERAGE_DEMAND_SOURCE_CONTEXT,
        "operational_unit": UNIT,
        "binding_version": 1,
        "active": True,
    }
    values.update(overrides)
    return PlanningOperationalUnitBinding.model_validate(values)


class BindingProvider:
    def __init__(self, binding=None, error: Exception | None = None):
        self.binding = binding or _binding()
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def resolve_binding(self, *, organization_id, demand_source_context):
        self.calls.append((organization_id, demand_source_context))
        if self.error is not None:
            raise self.error
        return self.binding


def _provider(rows, **overrides):
    calls: list[tuple[str, str, str]] = []

    def reader(organization_id, period_start, period_end):
        calls.append((organization_id, period_start, period_end))
        return tuple(rows)

    dependencies = {
        "coverage_reader": reader,
        "binding_provider": BindingProvider(),
        "policy": AmazonShiftTimeWindowPolicyProvider(),
    }
    dependencies.update(overrides)
    return AmazonOperationalDemandProviderAdapter(**dependencies), calls


def _get(provider, **overrides):
    values = {
        "organization_id": ORG,
        "period_start": START,
        "period_end": END,
        "operational_unit": UNIT,
    }
    values.update(overrides)
    return provider.get_demands(**values)


def test_adapter_implements_operational_demand_provider_protocol():
    provider, _ = _provider([])

    assert isinstance(provider, OperationalDemandProvider)


def test_reader_and_binding_resolver_are_each_called_once():
    binding_provider = BindingProvider()
    provider, reader_calls = _provider(
        [_row(), _row(cycle="SAME_DAY", segment="A")],
        binding_provider=binding_provider,
    )

    result = _get(provider)

    assert len(result) == 2
    assert reader_calls == [(ORG, START.isoformat(), END.isoformat())]
    assert binding_provider.calls == [
        (ORG, AMAZON_COVERAGE_DEMAND_SOURCE_CONTEXT)
    ]


def test_mapper_and_converter_are_called_once_per_row():
    rows = [_row(), _row(cycle="SAME_DAY", segment="A")]
    mapper_calls = []
    converter_calls = []

    def mapper(row, binding):
        mapper_calls.append((row, binding))
        return map_coverage_demand_to_amazon_input(row, binding)

    def converter(input_data, policy):
        converter_calls.append((input_data, policy))
        return convert_amazon_operational_demand(input_data, policy)

    provider, _ = _provider(
        rows,
        input_mapper=mapper,
        demand_converter=converter,
    )

    result = _get(provider)

    assert len(result) == 2
    assert len(mapper_calls) == len(rows)
    assert len(converter_calls) == len(rows)


def test_forecast_76_is_buffered_exactly_once():
    provider, _ = _provider([_row(forecast_routes=76)])

    demand = _get(provider)[0]

    assert demand.base_quantity == 76
    assert demand.target_quantity == 84
    assert demand.target_quantity != 92


def test_all_supported_buckets_use_f4_and_c3_mapping():
    provider, _ = _provider(
        [
            _row(cycle="NEXT_DAY", segment=None),
            _row(
                cycle="SAME_DAY",
                segment="A",
                source_identity="forecast-import:same-day-a",
            ),
            _row(
                cycle="SAME_DAY",
                segment="B_C",
                source_identity="forecast-import:same-day-b-c",
            ),
        ]
    )

    demands = _get(provider)

    assert {item.capability_or_workload for item in demands} == {
        "amazon-workload-next-day",
        "amazon-workload-same-day-a",
        "amazon-workload-same-day-b-c",
    }


def test_matching_binding_unit_is_accepted():
    provider, _ = _provider([_row()])

    demand = _get(provider)[0]

    assert demand.operational_unit.external_identifier == "DLO2"


def test_different_binding_unit_is_rejected_before_mapping():
    binding_provider = BindingProvider(
        _binding(
            operational_unit=OperationalUnit(
                external_identifier="OTHER",
            )
        )
    )
    provider, _ = _provider(
        [_row()],
        binding_provider=binding_provider,
    )

    with pytest.raises(
        AmazonOperationalDemandProviderValidationError,
        match="does not match the requested unit",
    ):
        _get(provider)


def test_binding_organization_mismatch_is_rejected():
    provider, _ = _provider(
        [_row()],
        binding_provider=BindingProvider(
            _binding(organization_id="organization-two")
        ),
    )

    with pytest.raises(
        AmazonOperationalDemandProviderValidationError,
        match="organization mismatch",
    ):
        _get(provider)


@pytest.mark.parametrize(
    "binding",
    (
        _binding(active=False),
        _binding(demand_source_context="another-context"),
    ),
)
def test_inactive_or_wrong_context_binding_is_rejected(binding):
    provider, _ = _provider(
        [],
        binding_provider=BindingProvider(binding),
    )

    with pytest.raises(AmazonOperationalDemandProviderValidationError):
        _get(provider)


def test_station_none_is_resolved_only_through_explicit_binding():
    provider, _ = _provider([_row(station=None)])

    demand = _get(provider)[0]

    assert demand.operational_unit == UNIT


def test_incompatible_row_station_propagates_f4_error():
    provider, _ = _provider([_row(station="OTHER")])

    with pytest.raises(AmazonCoverageDemandBindingError):
        _get(provider)


def test_suspect_authority_is_preserved_in_provenance():
    provider, _ = _provider(
        [
            _row(
                authority_status=ForecastAuthorityStatus.SUSPECT_TEMPLATE,
                detection_reason="CORRELATED_CONSTANT_BLOCK",
            )
        ]
    )

    demand = _get(provider)[0]

    assert '"authority_status":"SUSPECT_TEMPLATE"' in demand.source
    assert '"detection_reason":"CORRELATED_CONSTANT_BLOCK"' in demand.source


def test_reader_error_is_not_silenced_and_resolver_is_not_called():
    expected = RuntimeError("reader failed")
    binding_provider = BindingProvider()

    def reader(*_args):
        raise expected

    provider = AmazonOperationalDemandProviderAdapter(
        coverage_reader=reader,
        binding_provider=binding_provider,
    )

    with pytest.raises(RuntimeError, match="reader failed") as caught:
        _get(provider)

    assert caught.value is expected
    assert binding_provider.calls == []


def test_resolver_error_is_not_silenced():
    expected = RuntimeError("resolver failed")
    provider, _ = _provider(
        [_row()],
        binding_provider=BindingProvider(error=expected),
    )

    with pytest.raises(RuntimeError, match="resolver failed") as caught:
        _get(provider)

    assert caught.value is expected


def test_mapper_error_is_not_silenced():
    expected = AmazonCoverageDemandInputMappingError("mapper failed")

    def mapper(*_args):
        raise expected

    provider, _ = _provider([_row()], input_mapper=mapper)

    with pytest.raises(
        AmazonCoverageDemandInputMappingError,
        match="mapper failed",
    ) as caught:
        _get(provider)

    assert caught.value is expected


def test_converter_error_is_not_silenced_and_no_partial_tuple_is_returned():
    calls = []
    expected = RuntimeError("converter failed")

    def converter(input_data, policy):
        calls.append(input_data)
        if len(calls) == 2:
            raise expected
        return convert_amazon_operational_demand(input_data, policy)

    provider, _ = _provider(
        [_row(), _row(cycle="SAME_DAY", segment="A")],
        demand_converter=converter,
    )

    with pytest.raises(RuntimeError, match="converter failed") as caught:
        _get(provider)

    assert caught.value is expected
    assert len(calls) == 2


def test_final_organization_validation_rejects_invalid_converter_output():
    def converter(input_data, _policy):
        return OperationalDemand(
            organization_id="organization-two",
            operational_unit=input_data.operational_unit,
            date=input_data.date,
            time_window=TimeWindow(external_identifier="window"),
            capability_or_workload="capability",
            base_quantity=input_data.base_quantity,
            target_quantity=input_data.base_quantity,
            source=input_data.source,
            applied_policy=AppliedPolicyMetadata(identifier="test"),
        )

    provider, _ = _provider([_row()], demand_converter=converter)

    with pytest.raises(
        AmazonOperationalDemandProviderValidationError,
        match="organization mismatch",
    ):
        _get(provider)


def test_final_unit_validation_rejects_invalid_converter_output():
    def converter(input_data, _policy):
        return OperationalDemand(
            organization_id=input_data.organization_id,
            operational_unit=OperationalUnit(external_identifier="OTHER"),
            date=input_data.date,
            time_window=TimeWindow(external_identifier="window"),
            capability_or_workload="capability",
            base_quantity=input_data.base_quantity,
            target_quantity=input_data.base_quantity,
            source=input_data.source,
        )

    provider, _ = _provider([_row()], demand_converter=converter)

    with pytest.raises(
        AmazonOperationalDemandProviderValidationError,
        match="unit mismatch",
    ):
        _get(provider)


def test_output_order_is_deterministic_and_independent_of_reader_order():
    rows = [
        _row(
            operational_date="2026-08-25",
            cycle="SAME_DAY",
            segment="B_C",
            source_identity="third",
        ),
        _row(
            operational_date="2026-08-24",
            cycle="SAME_DAY",
            segment="A",
            source_identity="second",
        ),
        _row(
            operational_date="2026-08-24",
            cycle="NEXT_DAY",
            segment=None,
            source_identity="first",
        ),
    ]
    first_provider, _ = _provider(rows)
    second_provider, _ = _provider(reversed(rows))

    first = _get(first_provider)
    second = _get(second_provider)

    assert first == second
    assert tuple(item.date for item in first) == (
        date(2026, 8, 24),
        date(2026, 8, 24),
        date(2026, 8, 25),
    )


def test_core_remains_free_of_amazon_and_dsp_dependencies():
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
