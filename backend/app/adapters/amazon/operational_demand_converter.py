from datetime import date as CalendarDate
from decimal import Decimal, ROUND_HALF_UP

from pydantic import BaseModel, ConfigDict, Field

from app.domain.core_language import OperationalUnit, TimeWindow
from app.domain.workforce_auto_planning import (
    AppliedPolicyAttribute,
    AppliedPolicyMetadata,
    OperationalDemand,
    WorkforcePlanningPolicyProvider,
    WorkloadCapabilityMapping,
)


class AmazonOperationalDemandInput(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    organization_id: str = Field(min_length=1)
    operational_unit: OperationalUnit
    date: CalendarDate
    workload_bucket: str = Field(min_length=1)
    base_quantity: int = Field(ge=0)
    source: str = Field(min_length=1)


class UnknownAmazonWorkloadError(ValueError):
    pass


class AmazonPolicyMappingError(ValueError):
    pass


def _workload_mapping(
    workload_bucket: str,
    policy: WorkforcePlanningPolicyProvider,
) -> WorkloadCapabilityMapping:
    matches = tuple(
        item
        for item in policy.workload_capability_mappings()
        if item.workload_identifier == workload_bucket
    )
    if not matches:
        raise UnknownAmazonWorkloadError(
            f"Unsupported Amazon workload bucket: {workload_bucket}"
        )
    if len(matches) != 1:
        raise AmazonPolicyMappingError(
            f"Ambiguous Amazon workload mapping: {workload_bucket}"
        )
    return matches[0]


def _time_window(
    mapping: WorkloadCapabilityMapping,
    policy: WorkforcePlanningPolicyProvider,
) -> TimeWindow:
    window_identifiers = {
        shift.time_window_identifier
        for shift in policy.shift_catalogue()
        if shift.required_capabilities == mapping.required_capabilities
    }
    if len(window_identifiers) != 1:
        raise AmazonPolicyMappingError(
            f"Amazon workload must resolve to one time window: "
            f"{mapping.workload_identifier}"
        )
    identifier = next(iter(window_identifiers))
    windows = tuple(
        window
        for window in policy.time_windows()
        if window.external_identifier == identifier
    )
    if len(windows) != 1:
        raise AmazonPolicyMappingError(
            f"Amazon time window mapping is missing or ambiguous: {identifier}"
        )
    return windows[0]


def _single_required_capability(
    mapping: WorkloadCapabilityMapping,
) -> str:
    if len(mapping.required_capabilities) != 1:
        raise AmazonPolicyMappingError(
            f"Amazon workload must resolve to exactly one capability: "
            f"{mapping.workload_identifier}"
        )
    return mapping.required_capabilities[0]


def _target_quantity(base_quantity: int, target_multiplier: Decimal) -> int:
    return int(
        (Decimal(base_quantity) * target_multiplier).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def convert_amazon_operational_demand(
    input_data: AmazonOperationalDemandInput,
    policy: WorkforcePlanningPolicyProvider,
) -> OperationalDemand:
    mapping = _workload_mapping(input_data.workload_bucket, policy)
    capability = _single_required_capability(mapping)
    time_window = _time_window(mapping, policy)
    buffer_policy = policy.operational_buffer_policy()

    return OperationalDemand(
        organization_id=input_data.organization_id,
        operational_unit=input_data.operational_unit,
        date=input_data.date,
        time_window=time_window,
        capability_or_workload=capability,
        base_quantity=input_data.base_quantity,
        target_quantity=_target_quantity(
            input_data.base_quantity,
            buffer_policy.target_multiplier,
        ),
        source=input_data.source,
        applied_policy=AppliedPolicyMetadata(
            identifier=buffer_policy.identifier,
            attributes=(
                AppliedPolicyAttribute(
                    key="target_multiplier",
                    value=format(buffer_policy.target_multiplier, "f"),
                ),
                AppliedPolicyAttribute(
                    key="rounding",
                    value="ROUND_HALF_UP",
                ),
            ),
        ),
    )
