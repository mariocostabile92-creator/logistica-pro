from datetime import date, datetime
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.domain.core_language import (
    AssetReference,
    HumanResource,
    ResourceAvailability,
)
from app.domain.execution_attempt import ExecutionAttempt
from app.domain.execution_intent import (
    ExecutionIntent,
    ExecutionPublicationReference,
)
from app.domain.planning_inputs import PlanningResourceCapability
from app.domain.runtime_authority import AuthorityResolutionResult


PLANNING_RUNTIME_OUTPUT_CONTRACT_VERSION = "1.0"


class _PlanningRuntimeModel(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)


def _timezone_aware(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("A timezone-aware datetime is required.")
    return value


class PlanningRuntimeOutputStatus(str, Enum):
    READY = "READY"
    REJECTED = "REJECTED"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class PlanningRuntimeDiagnosticSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class PlanningRuntimeScope(_PlanningRuntimeModel):
    organization_id: str = Field(min_length=1, max_length=120)
    operational_unit_id: str = Field(min_length=1, max_length=120)
    planning_date: date
    timezone: str = Field(min_length=1, max_length=120)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA identifier.") from exc
        return value

    @property
    def identity(self) -> tuple[str, str, date, str]:
        return (
            self.organization_id,
            self.operational_unit_id,
            self.planning_date,
            self.timezone,
        )


class PlanningRuntimeOutputVersion(_PlanningRuntimeModel):
    contract_version: str = PLANNING_RUNTIME_OUTPUT_CONTRACT_VERSION
    sequence: int = Field(ge=1)


class PlanningRuntimeAssignment(_PlanningRuntimeModel):
    task_identifier: str = Field(min_length=1, max_length=200)
    resource_identifier: str | None = Field(default=None, max_length=200)
    asset_identifier: str | None = Field(default=None, max_length=200)
    state: str = Field(min_length=1, max_length=80)


class PlanningRuntimeOutputMetadata(_PlanningRuntimeModel):
    producer: str = Field(
        default="planning-runtime-producer",
        min_length=1,
        max_length=120,
    )
    contract_version: str = PLANNING_RUNTIME_OUTPUT_CONTRACT_VERSION
    source: str = Field(default="published-plan", min_length=1, max_length=120)
    publication_id: str = Field(min_length=1, max_length=120)
    publication_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration_version: str = Field(min_length=1, max_length=120)
    rules_version: str = Field(min_length=1, max_length=120)
    generated_at: datetime

    _validate_generated_at = field_validator("generated_at")(
        _timezone_aware
    )


class PlanningRuntimeProducerInput(_PlanningRuntimeModel):
    scope: PlanningRuntimeScope
    publication: ExecutionPublicationReference
    planning_version: int = Field(ge=1)
    output_version: PlanningRuntimeOutputVersion
    resources: tuple[HumanResource, ...] = Field(
        default_factory=tuple,
        max_length=20_000,
    )
    fleet: tuple[AssetReference, ...] = Field(
        default_factory=tuple,
        max_length=20_000,
    )
    assignments: tuple[PlanningRuntimeAssignment, ...] = Field(
        default_factory=tuple,
        max_length=20_000,
    )
    capabilities: tuple[PlanningResourceCapability, ...] = Field(
        default_factory=tuple,
        max_length=20_000,
    )
    availability: tuple[ResourceAvailability, ...] = Field(
        default_factory=tuple,
        max_length=20_000,
    )
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration_version: str = Field(min_length=1, max_length=120)
    rules_version: str = Field(min_length=1, max_length=120)
    evaluation_at: datetime

    _validate_evaluation_at = field_validator("evaluation_at")(
        _timezone_aware
    )


class PlanningRuntimeOutput(_PlanningRuntimeModel):
    scope: PlanningRuntimeScope
    planning_version: int = Field(ge=1)
    publication_version: int = Field(ge=1)
    version: PlanningRuntimeOutputVersion
    resources: tuple[HumanResource, ...] = Field(
        default_factory=tuple,
        max_length=20_000,
    )
    fleet: tuple[AssetReference, ...] = Field(
        default_factory=tuple,
        max_length=20_000,
    )
    assignments: tuple[PlanningRuntimeAssignment, ...] = Field(
        default_factory=tuple,
        max_length=20_000,
    )
    capabilities: tuple[PlanningResourceCapability, ...] = Field(
        default_factory=tuple,
        max_length=20_000,
    )
    availability: tuple[ResourceAvailability, ...] = Field(
        default_factory=tuple,
        max_length=20_000,
    )
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    metadata: PlanningRuntimeOutputMetadata

    @model_validator(mode="after")
    def validate_contract_version(self):
        if self.version.contract_version != self.metadata.contract_version:
            raise ValueError("Output and metadata contract versions must match.")
        return self


class PlanningRuntimeSnapshot(_PlanningRuntimeModel):
    snapshot_id: str = Field(min_length=1, max_length=120)
    output: PlanningRuntimeOutput
    snapshot_size_bytes: int = Field(ge=1)


class PlanningRuntimeOutputDiagnostic(_PlanningRuntimeModel):
    code: str = Field(min_length=1, max_length=120)
    severity: PlanningRuntimeDiagnosticSeverity
    message: str = Field(min_length=1, max_length=500)
    field: str | None = Field(default=None, max_length=200)


class PlanningRuntimeOutputDiagnostics(_PlanningRuntimeModel):
    valid: bool
    items: tuple[PlanningRuntimeOutputDiagnostic, ...] = Field(
        default_factory=tuple,
        max_length=100,
    )
    generated_at: datetime

    _validate_generated_at = field_validator("generated_at")(
        _timezone_aware
    )

    @model_validator(mode="after")
    def validate_status(self):
        contains_error = any(
            item.severity is PlanningRuntimeDiagnosticSeverity.ERROR
            for item in self.items
        )
        if self.valid == contains_error:
            raise ValueError("Diagnostics validity must reflect errors.")
        return self


class PlanningRuntimeProducerMetrics(_PlanningRuntimeModel):
    producer_latency_ms: float = Field(ge=0)
    generation_time_ms: float = Field(ge=0)
    snapshot_size_bytes: int = Field(ge=1)
    parity_percent: float | None = Field(default=None, ge=0, le=100)


class PlanningRuntimeProducerResult(_PlanningRuntimeModel):
    status: PlanningRuntimeOutputStatus
    snapshot: PlanningRuntimeSnapshot | None = None
    metrics: PlanningRuntimeProducerMetrics | None = None
    diagnostics: PlanningRuntimeOutputDiagnostics
    generated_at: datetime

    _validate_generated_at = field_validator("generated_at")(
        _timezone_aware
    )

    @model_validator(mode="after")
    def validate_result(self):
        if self.status is PlanningRuntimeOutputStatus.READY:
            if self.snapshot is None or self.metrics is None:
                raise ValueError("READY requires snapshot and metrics.")
            if not self.diagnostics.valid:
                raise ValueError("READY requires valid diagnostics.")
        elif self.snapshot is not None or self.metrics is not None:
            raise ValueError("Rejected or unavailable output must be empty.")
        return self


class PlanningRuntimeProductionContext(_PlanningRuntimeModel):
    source: PlanningRuntimeProducerInput
    authority: AuthorityResolutionResult
    intent: ExecutionIntent
    attempt: ExecutionAttempt | None
