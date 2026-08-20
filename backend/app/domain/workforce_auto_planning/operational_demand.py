from datetime import date as CalendarDate

from pydantic import BaseModel, ConfigDict, Field

from app.domain.core_language import OperationalUnit, TimeWindow


MetadataValue = str | int | float | bool | None


class _ImmutableDemandModel(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)


class AppliedPolicyAttribute(_ImmutableDemandModel):
    key: str = Field(min_length=1)
    value: MetadataValue


class AppliedPolicyMetadata(_ImmutableDemandModel):
    identifier: str = Field(min_length=1)
    version: str | None = Field(default=None, min_length=1)
    attributes: tuple[AppliedPolicyAttribute, ...] = Field(default_factory=tuple)


class OperationalDemand(_ImmutableDemandModel):
    organization_id: str = Field(min_length=1)
    operational_unit: OperationalUnit
    date: CalendarDate
    time_window: TimeWindow
    capability_or_workload: str = Field(min_length=1)
    base_quantity: int = Field(ge=0)
    target_quantity: int = Field(ge=0)
    source: str = Field(min_length=1)
    applied_policy: AppliedPolicyMetadata | None = None
