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

from app.domain.execution_intent import ExecutionPublicationStatus


class _RuntimeShadowModel(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)


class RuntimeShadowSource(str, Enum):
    LEGACY = "LEGACY"
    RUNTIME = "RUNTIME"


class RuntimeShadowState(str, Enum):
    NOT_AVAILABLE = "NOT_AVAILABLE"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"


class PlanningMismatchCategory(str, Enum):
    RESOURCE = "RESOURCE"
    FLEET = "FLEET"
    CAPABILITY = "CAPABILITY"
    ASSIGNMENT = "ASSIGNMENT"
    VERSION = "VERSION"
    FINGERPRINT = "FINGERPRINT"
    SCOPE = "SCOPE"
    VALIDATION = "VALIDATION"
    UNKNOWN = "UNKNOWN"


class PlanningMismatchSeverity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RuntimeShadowDiagnosticSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


def _timezone_aware(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("A timezone-aware datetime is required.")
    return value


class RuntimeShadowScope(_RuntimeShadowModel):
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


class RuntimeShadowPublication(_RuntimeShadowModel):
    publication_id: str = Field(min_length=1, max_length=120)
    publication_version: int = Field(ge=1)
    status: ExecutionPublicationStatus = ExecutionPublicationStatus.PUBLISHED


class RuntimeShadowSnapshot(_RuntimeShadowModel):
    source: RuntimeShadowSource
    scope: RuntimeShadowScope
    publication: RuntimeShadowPublication
    planning_version: int = Field(ge=1)
    resources: tuple[str, ...] = Field(default_factory=tuple, max_length=20_000)
    fleet: tuple[str, ...] = Field(default_factory=tuple, max_length=20_000)
    assignments: tuple[str, ...] = Field(
        default_factory=tuple,
        max_length=20_000,
    )
    capabilities: tuple[str, ...] = Field(
        default_factory=tuple,
        max_length=20_000,
    )
    availability: tuple[str, ...] = Field(
        default_factory=tuple,
        max_length=20_000,
    )
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration_version: str = Field(min_length=1, max_length=120)
    rules_version: str = Field(min_length=1, max_length=120)
    validation_errors: tuple[str, ...] = Field(
        default_factory=tuple,
        max_length=100,
    )
    evaluation_at: datetime
    generated_at: datetime

    _validate_evaluation_at = field_validator("evaluation_at")(
        _timezone_aware
    )
    _validate_generated_at = field_validator("generated_at")(
        _timezone_aware
    )


class PlanningMismatch(_RuntimeShadowModel):
    id: str = Field(min_length=1, max_length=120)
    category: PlanningMismatchCategory
    severity: PlanningMismatchSeverity
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=500)
    legacy_value: str = Field(max_length=1_000)
    runtime_value: str = Field(max_length=1_000)
    difference: str = Field(min_length=1, max_length=1_000)
    scope: RuntimeShadowScope
    publication: RuntimeShadowPublication
    timestamp: datetime
    suggested_action: str = Field(min_length=1, max_length=500)

    _validate_timestamp = field_validator("timestamp")(_timezone_aware)


class PlanningMismatchDistribution(_RuntimeShadowModel):
    category: PlanningMismatchCategory
    count: int = Field(ge=1)


class PlanningParityReport(_RuntimeShadowModel):
    parity_percent: float = Field(ge=0, le=100)
    mismatch_percent: float = Field(ge=0, le=100)
    perfect_match: bool
    comparable: bool
    total_comparisons: int = Field(ge=1)
    total_mismatches: int = Field(ge=0)
    missing: int = Field(ge=0)
    unexpected: int = Field(ge=0)
    mismatch_distribution: tuple[PlanningMismatchDistribution, ...] = Field(
        default_factory=tuple,
        max_length=20,
    )
    comparison_time_ms: float = Field(ge=0)
    planning_version: int = Field(ge=1)
    publication_version: int = Field(ge=1)
    operational_unit: str = Field(min_length=1, max_length=120)
    planning_date: date
    parity_target_met: bool

    @model_validator(mode="after")
    def validate_report(self):
        if abs((self.parity_percent + self.mismatch_percent) - 100) > 0.02:
            raise ValueError("Parity and mismatch percentages must total 100.")
        if self.total_mismatches > self.total_comparisons:
            raise ValueError("Mismatch count cannot exceed comparison count.")
        if self.perfect_match != (
            self.comparable and self.total_mismatches == 0
        ):
            raise ValueError("Perfect match must be comparable and mismatch-free.")
        return self


class PlanningComparatorResult(_RuntimeShadowModel):
    report: PlanningParityReport
    mismatches: tuple[PlanningMismatch, ...] = Field(
        default_factory=tuple,
        max_length=100,
    )
    compared_at: datetime

    _validate_compared_at = field_validator("compared_at")(_timezone_aware)

    @model_validator(mode="after")
    def validate_mismatch_count(self):
        if self.report.total_mismatches != len(self.mismatches):
            raise ValueError("Report mismatch count must match mismatch details.")
        return self


class RuntimeShadowMetrics(_RuntimeShadowModel):
    parity_percent: float = Field(ge=0, le=100)
    critical_mismatch: int = Field(ge=0)
    high_mismatch: int = Field(ge=0)
    execution_simulated: bool = True
    comparison_time_ms: float = Field(ge=0)
    shadow_latency_ms: float = Field(ge=0)
    duplicate_execution: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_shadow_only(self):
        if not self.execution_simulated:
            raise ValueError("Runtime Shadow must remain simulated.")
        if self.duplicate_execution != 0:
            raise ValueError("Runtime Shadow cannot execute or duplicate writes.")
        return self


class RuntimeShadowDiagnostic(_RuntimeShadowModel):
    code: str = Field(min_length=1, max_length=120)
    severity: RuntimeShadowDiagnosticSeverity
    message: str = Field(min_length=1, max_length=500)


class RuntimeShadowDiagnostics(_RuntimeShadowModel):
    items: tuple[RuntimeShadowDiagnostic, ...] = Field(
        default_factory=tuple,
        max_length=20,
    )
    generated_at: datetime

    _validate_generated_at = field_validator("generated_at")(_timezone_aware)


class RuntimeShadowResult(_RuntimeShadowModel):
    state: RuntimeShadowState
    report: PlanningParityReport | None = None
    mismatches: tuple[PlanningMismatch, ...] = Field(
        default_factory=tuple,
        max_length=100,
    )
    metrics: RuntimeShadowMetrics | None = None
    diagnostics: RuntimeShadowDiagnostics
    generated_at: datetime

    _validate_generated_at = field_validator("generated_at")(_timezone_aware)

    @model_validator(mode="after")
    def validate_result(self):
        if self.state is RuntimeShadowState.COMPLETED:
            if self.report is None or self.metrics is None:
                raise ValueError("Completed Shadow requires report and metrics.")
            if self.report.total_mismatches != len(self.mismatches):
                raise ValueError("Shadow mismatch details must match the report.")
        elif self.report is not None or self.metrics is not None:
            raise ValueError("Incomplete Shadow cannot expose report or metrics.")
        return self
