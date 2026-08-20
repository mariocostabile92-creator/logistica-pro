from datetime import date
import json

from app.adapters.amazon.operational_demand_converter import (
    AmazonOperationalDemandInput,
)
from app.domain.workforce_auto_planning import (
    PlanningOperationalUnitBinding,
)
from app.plugins.workforce.domain.coverage import EffectiveCoverageDemandRow


AMAZON_COVERAGE_DEMAND_SOURCE_CONTEXT = (
    "amazon-effective-coverage-demand"
)
_PROVENANCE_PREFIX = "coverage:"
_WORKLOAD_BUCKETS = {
    ("NEXT_DAY", None): "NEXT_DAY",
    ("SAME_DAY", "A"): "SAME_DAY:A",
    ("SAME_DAY", "B_C"): "SAME_DAY:B_C",
}


class AmazonCoverageDemandInputMappingError(ValueError):
    pass


class AmazonCoverageDemandBindingError(
    AmazonCoverageDemandInputMappingError
):
    pass


class UnknownAmazonCoverageDemandBucketError(
    AmazonCoverageDemandInputMappingError
):
    pass


def _validate_binding(
    row: EffectiveCoverageDemandRow,
    binding: PlanningOperationalUnitBinding,
) -> None:
    if not binding.active:
        raise AmazonCoverageDemandBindingError(
            "Planning operational unit binding is inactive."
        )
    if binding.organization_id != row.organization_id:
        raise AmazonCoverageDemandBindingError(
            "Coverage demand and binding organizations do not match."
        )
    if (
        binding.demand_source_context
        != AMAZON_COVERAGE_DEMAND_SOURCE_CONTEXT
    ):
        raise AmazonCoverageDemandBindingError(
            "Planning operational unit binding context is not supported."
        )
    if (
        row.station is not None
        and row.station
        != binding.operational_unit.external_identifier
    ):
        raise AmazonCoverageDemandBindingError(
            "Coverage station does not match the bound operational unit."
        )


def _workload_bucket(row: EffectiveCoverageDemandRow) -> str:
    try:
        return _WORKLOAD_BUCKETS[(row.cycle, row.segment)]
    except KeyError as exc:
        raise UnknownAmazonCoverageDemandBucketError(
            "Unsupported Coverage cycle and segment: "
            f"{row.cycle}/{row.segment}"
        ) from exc


def _source_provenance(row: EffectiveCoverageDemandRow) -> str:
    provenance = {
        "authority_status": row.authority_status.value,
        "source": row.source,
        "source_identity": row.source_identity,
    }
    if row.detection_reason is not None:
        provenance["detection_reason"] = row.detection_reason
    return _PROVENANCE_PREFIX + json.dumps(
        provenance,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def map_coverage_demand_to_amazon_input(
    row: EffectiveCoverageDemandRow,
    binding: PlanningOperationalUnitBinding,
) -> AmazonOperationalDemandInput:
    _validate_binding(row, binding)
    if row.forecast_routes < 0:
        raise AmazonCoverageDemandInputMappingError(
            "Coverage forecast_routes cannot be negative."
        )
    try:
        operational_date = date.fromisoformat(row.operational_date)
    except ValueError as exc:
        raise AmazonCoverageDemandInputMappingError(
            "Coverage operational_date must be an ISO date."
        ) from exc

    return AmazonOperationalDemandInput(
        organization_id=row.organization_id,
        operational_unit=binding.operational_unit,
        date=operational_date,
        workload_bucket=_workload_bucket(row),
        base_quantity=row.forecast_routes,
        source=_source_provenance(row),
    )
