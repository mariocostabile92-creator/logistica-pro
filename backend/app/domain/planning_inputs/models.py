from datetime import date, datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.core_language import (
    AssetReference,
    HumanResource,
    OperationalUnit,
    ResourceAvailability,
    ResourceKind,
    TimeWindow,
)


PLANNING_INPUT_CONTRACT_VERSION = "1.0"


class _PlanningInputModel(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)


def _require_timezone(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("A timezone-aware datetime is required.")
    return value


class PlanningInputType(str, Enum):
    WORKFORCE = "workforce"
    FLEET = "fleet"


class PlanningInputStatus(str, Enum):
    READY = "ready"
    STALE = "stale"
    PARTIAL = "partial"
    MISSING = "missing"
    INVALID = "invalid"


class PlanningInputProvenance(str, Enum):
    PUBLIC_CONTRACT = "public_contract"
    CORE_PROJECTION = "core_projection"


class PlanningInputSource(_PlanningInputModel):
    producer: str = Field(min_length=1)
    contract_name: str = Field(min_length=1)
    contract_version: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)
    provenance: PlanningInputProvenance
    produced_at: datetime

    _validate_produced_at = field_validator("produced_at")(_require_timezone)


class PlanningInputScope(_PlanningInputModel):
    organization_id: str = Field(min_length=1)
    operational_unit: OperationalUnit
    operation_date: date

    @property
    def identity(self) -> tuple[str, str, date]:
        return (
            self.organization_id,
            self.operational_unit.external_identifier,
            self.operation_date,
        )


class PlanningInputVersion(_PlanningInputModel):
    value: str = Field(min_length=1)
    sequence: int | None = Field(default=None, ge=1)


class PlanningInputFreshness(_PlanningInputModel):
    observed_at: datetime
    expires_at: datetime

    _validate_observed_at = field_validator("observed_at")(_require_timezone)
    _validate_expires_at = field_validator("expires_at")(_require_timezone)

    @model_validator(mode="after")
    def validate_interval(self):
        if self.expires_at < self.observed_at:
            raise ValueError("expires_at cannot precede observed_at.")
        return self


class PlanningInputMetadata(_PlanningInputModel):
    input_type: PlanningInputType
    source: PlanningInputSource
    scope: PlanningInputScope
    version: PlanningInputVersion
    freshness: PlanningInputFreshness


class PlanningResourceCapability(_PlanningInputModel):
    resource_identifier: str = Field(min_length=1)
    resource_kind: ResourceKind
    capability: str = Field(min_length=1)


class PlanningCoverage(_PlanningInputModel):
    required: int | None = Field(default=None, ge=0)
    available: int = Field(ge=0)
    scheduled: int = Field(ge=0)
    unavailable: int = Field(ge=0)
    margin: int | None = None
    status: str = Field(min_length=1)
    limitations: tuple[str, ...] = Field(default_factory=tuple)


class PlanningAssetRegistry(_PlanningInputModel):
    assets: tuple[AssetReference, ...] = Field(default_factory=tuple)


class WorkforcePlanningInput(_PlanningInputModel):
    input_type: Literal[PlanningInputType.WORKFORCE] = (
        PlanningInputType.WORKFORCE
    )
    human_resources: tuple[HumanResource, ...] = Field(default_factory=tuple)
    availability: tuple[ResourceAvailability, ...] = Field(
        default_factory=tuple
    )
    capabilities: tuple[PlanningResourceCapability, ...] = Field(
        default_factory=tuple
    )
    coverage: PlanningCoverage | None = None
    time_windows: tuple[TimeWindow, ...] = Field(default_factory=tuple)


class FleetPlanningInput(_PlanningInputModel):
    input_type: Literal[PlanningInputType.FLEET] = PlanningInputType.FLEET
    registry: PlanningAssetRegistry
    availability: tuple[ResourceAvailability, ...] = Field(
        default_factory=tuple
    )
    capabilities: tuple[PlanningResourceCapability, ...] = Field(
        default_factory=tuple
    )


PlanningInputPayload = Annotated[
    WorkforcePlanningInput | FleetPlanningInput,
    Field(discriminator="input_type"),
]


class PlanningInputDependency(_PlanningInputModel):
    dependency_id: str = Field(min_length=1)
    producer: str = Field(min_length=1)
    required: bool = True
    satisfied: bool
    version: PlanningInputVersion | None = None
    source_reference: str | None = Field(default=None, min_length=1)


class PlanningInputContract(_PlanningInputModel):
    contract_version: str = PLANNING_INPUT_CONTRACT_VERSION
    metadata: PlanningInputMetadata
    payload: PlanningInputPayload
    dependencies: tuple[PlanningInputDependency, ...] = Field(
        default_factory=tuple
    )

    @model_validator(mode="after")
    def validate_input_type(self):
        if self.metadata.input_type != self.payload.input_type:
            raise ValueError("Metadata and payload input types must match.")
        return self


class PlanningInputValidationIssue(_PlanningInputModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    field: str | None = None
    blocking: bool = False


class PlanningInputValidation(_PlanningInputModel):
    status: PlanningInputStatus
    assessed_at: datetime
    issues: tuple[PlanningInputValidationIssue, ...] = Field(
        default_factory=tuple
    )

    _validate_assessed_at = field_validator("assessed_at")(_require_timezone)


class PlanningInputSnapshot(_PlanningInputModel):
    snapshot_id: str = Field(min_length=1)
    contract: PlanningInputContract
    validation: PlanningInputValidation


class PlanningInputEnvelope(_PlanningInputModel):
    contract_version: str = PLANNING_INPUT_CONTRACT_VERSION
    envelope_id: str = Field(min_length=1)
    scope: PlanningInputScope
    version: PlanningInputVersion
    created_at: datetime
    snapshots: tuple[PlanningInputSnapshot, ...] = Field(min_length=1)
    dependencies: tuple[PlanningInputDependency, ...] = Field(
        default_factory=tuple
    )

    _validate_created_at = field_validator("created_at")(_require_timezone)

    @model_validator(mode="after")
    def validate_envelope(self):
        input_types: list[PlanningInputType] = []
        for snapshot in self.snapshots:
            metadata = snapshot.contract.metadata
            if metadata.scope.identity != self.scope.identity:
                raise ValueError("All snapshots must share the envelope scope.")
            input_types.append(metadata.input_type)
        if len(input_types) != len(set(input_types)):
            raise ValueError("An envelope cannot repeat an input type.")
        return self

    @property
    def operational_unit(self) -> OperationalUnit:
        return self.scope.operational_unit

    @property
    def planning_date(self) -> date:
        return self.scope.operation_date

    @property
    def fingerprint(self) -> str:
        return self.version.value

    @property
    def freshness(self) -> tuple[PlanningInputFreshness, ...]:
        return tuple(
            snapshot.contract.metadata.freshness
            for snapshot in self.snapshots
        )

    @property
    def validation(self) -> tuple[PlanningInputValidation, ...]:
        return tuple(snapshot.validation for snapshot in self.snapshots)

    @property
    def metadata(self) -> tuple[PlanningInputMetadata, ...]:
        return tuple(
            snapshot.contract.metadata for snapshot in self.snapshots
        )
