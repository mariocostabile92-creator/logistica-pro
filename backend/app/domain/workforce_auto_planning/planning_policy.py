from decimal import Decimal
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from app.domain.core_language import TimeWindow


PolicyParameterValue = str | int | float | bool | None


class _ImmutablePolicyModel(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)


class OperationalBufferPolicy(_ImmutablePolicyModel):
    identifier: str = Field(min_length=1)
    target_multiplier: Decimal = Field(gt=0)


class ShiftCatalogueEntry(_ImmutablePolicyModel):
    identifier: str = Field(min_length=1)
    label: str = Field(min_length=1)
    time_window_identifier: str = Field(min_length=1)
    required_capabilities: tuple[str, ...] = Field(default_factory=tuple)


class WorkloadCapabilityMapping(_ImmutablePolicyModel):
    workload_identifier: str = Field(min_length=1)
    required_capabilities: tuple[str, ...] = Field(min_length=1)


class PlanningPriorityOrPreference(_ImmutablePolicyModel):
    identifier: str = Field(min_length=1)
    priority: int = Field(ge=0)
    preference: str | None = Field(default=None, min_length=1)


class PlanningRuleParameter(_ImmutablePolicyModel):
    key: str = Field(min_length=1)
    value: PolicyParameterValue


class PlanningRuleDescriptor(_ImmutablePolicyModel):
    identifier: str = Field(min_length=1)
    parameters: tuple[PlanningRuleParameter, ...] = Field(default_factory=tuple)


@runtime_checkable
class WorkforcePlanningPolicyProvider(Protocol):
    def operational_buffer_policy(self) -> OperationalBufferPolicy: ...

    def shift_catalogue(self) -> tuple[ShiftCatalogueEntry, ...]: ...

    def time_windows(self) -> tuple[TimeWindow, ...]: ...

    def workload_capability_mappings(
        self,
    ) -> tuple[WorkloadCapabilityMapping, ...]: ...

    def priorities_and_preferences(
        self,
    ) -> tuple[PlanningPriorityOrPreference, ...]: ...

    def additional_rules(self) -> tuple[PlanningRuleDescriptor, ...]: ...
