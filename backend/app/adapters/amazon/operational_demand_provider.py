from collections.abc import Callable
from datetime import date as CalendarDate

from app.adapters.amazon.coverage_operational_demand_input_mapper import (
    AMAZON_COVERAGE_DEMAND_SOURCE_CONTEXT,
    map_coverage_demand_to_amazon_input,
)
from app.adapters.amazon.operational_demand_converter import (
    AmazonOperationalDemandInput,
    convert_amazon_operational_demand,
)
from app.adapters.amazon.shift_time_window_policy import (
    AmazonShiftTimeWindowPolicyProvider,
)
from app.core.configuration.planning_operational_unit_binding_provider import (
    ConfigurationPlanningOperationalUnitBindingProvider,
)
from app.domain.core_language import OperationalUnit
from app.domain.workforce_auto_planning import (
    OperationalDemand,
    PlanningOperationalUnitBinding,
    PlanningOperationalUnitBindingProvider,
    WorkforcePlanningPolicyProvider,
)
from app.plugins.workforce.domain.coverage import EffectiveCoverageDemandRow
from app.plugins.workforce.infrastructure.coverage_repository import (
    list_effective_coverage_demands,
)


CoverageDemandReader = Callable[
    [str, str, str],
    tuple[EffectiveCoverageDemandRow, ...],
]
CoverageDemandInputMapper = Callable[
    [EffectiveCoverageDemandRow, PlanningOperationalUnitBinding],
    AmazonOperationalDemandInput,
]
AmazonDemandConverter = Callable[
    [AmazonOperationalDemandInput, WorkforcePlanningPolicyProvider],
    OperationalDemand,
]


class AmazonOperationalDemandProviderValidationError(ValueError):
    pass


class AmazonOperationalDemandProviderAdapter:
    def __init__(
        self,
        *,
        coverage_reader: CoverageDemandReader | None = None,
        binding_provider: PlanningOperationalUnitBindingProvider | None = None,
        input_mapper: CoverageDemandInputMapper | None = None,
        demand_converter: AmazonDemandConverter | None = None,
        policy: WorkforcePlanningPolicyProvider | None = None,
    ) -> None:
        self._coverage_reader = (
            coverage_reader or list_effective_coverage_demands
        )
        self._binding_provider = (
            binding_provider
            or ConfigurationPlanningOperationalUnitBindingProvider()
        )
        self._input_mapper = (
            input_mapper or map_coverage_demand_to_amazon_input
        )
        self._demand_converter = (
            demand_converter or convert_amazon_operational_demand
        )
        self._policy = policy or AmazonShiftTimeWindowPolicyProvider()

    def get_demands(
        self,
        *,
        organization_id: str,
        period_start: CalendarDate,
        period_end: CalendarDate,
        operational_unit: OperationalUnit,
    ) -> tuple[OperationalDemand, ...]:
        if not isinstance(organization_id, str) or not organization_id.strip():
            raise AmazonOperationalDemandProviderValidationError(
                "organization_id cannot be empty"
            )
        if period_end < period_start:
            raise AmazonOperationalDemandProviderValidationError(
                "period_end cannot precede period_start"
            )
        requested_unit_identifier = (
            operational_unit.external_identifier
        )
        if (
            not isinstance(requested_unit_identifier, str)
            or not requested_unit_identifier.strip()
        ):
            raise AmazonOperationalDemandProviderValidationError(
                "operational_unit external_identifier cannot be empty"
            )
        organization = organization_id.strip()
        rows = self._coverage_reader(
            organization,
            period_start.isoformat(),
            period_end.isoformat(),
        )
        binding = self._binding_provider.resolve_binding(
            organization_id=organization,
            demand_source_context=AMAZON_COVERAGE_DEMAND_SOURCE_CONTEXT,
        )
        self._validate_binding(
            binding,
            organization_id=organization,
            operational_unit_identifier=requested_unit_identifier,
        )

        demands: list[OperationalDemand] = []
        for row in rows:
            input_data = self._input_mapper(row, binding)
            demand = self._demand_converter(input_data, self._policy)
            self._validate_demand(
                demand,
                organization_id=organization,
                operational_unit_identifier=requested_unit_identifier,
            )
            demands.append(demand)
        demands.sort(
            key=lambda demand: (
                demand.date,
                demand.time_window.external_identifier,
                demand.capability_or_workload,
                demand.source,
                demand.base_quantity,
                demand.target_quantity,
            )
        )
        return tuple(demands)

    @staticmethod
    def _validate_binding(
        binding: PlanningOperationalUnitBinding,
        *,
        organization_id: str,
        operational_unit_identifier: str,
    ) -> None:
        if not binding.active:
            raise AmazonOperationalDemandProviderValidationError(
                "Planning operational unit binding is inactive."
            )
        if binding.organization_id != organization_id:
            raise AmazonOperationalDemandProviderValidationError(
                "Planning operational unit binding organization mismatch."
            )
        if (
            binding.demand_source_context
            != AMAZON_COVERAGE_DEMAND_SOURCE_CONTEXT
        ):
            raise AmazonOperationalDemandProviderValidationError(
                "Planning operational unit binding context mismatch."
            )
        if (
            binding.operational_unit.external_identifier
            != operational_unit_identifier
        ):
            raise AmazonOperationalDemandProviderValidationError(
                "Planning operational unit binding does not match the requested unit."
            )

    @staticmethod
    def _validate_demand(
        demand: OperationalDemand,
        *,
        organization_id: str,
        operational_unit_identifier: str,
    ) -> None:
        if demand.organization_id != organization_id:
            raise AmazonOperationalDemandProviderValidationError(
                "Converted operational demand organization mismatch."
            )
        if (
            demand.operational_unit.external_identifier
            != operational_unit_identifier
        ):
            raise AmazonOperationalDemandProviderValidationError(
                "Converted operational demand unit mismatch."
            )
