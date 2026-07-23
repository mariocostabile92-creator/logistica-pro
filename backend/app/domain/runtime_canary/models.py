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

from app.domain.execution_attempt import ExecutionAttempt
from app.domain.execution_intent import (
    ExecutionIntent,
    ExecutionPublicationReference,
)
from app.domain.planning_runtime import PlanningRuntimeProducerResult
from app.domain.runtime_authority import AuthorityResolutionResult
from app.domain.runtime_shadow import PlanningMismatch, RuntimeShadowResult


class _RuntimeCanaryModel(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)


def _timezone_aware(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("A timezone-aware datetime is required.")
    return value


class RuntimeCanaryStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    OBSERVING = "OBSERVING"
    FINISHED = "FINISHED"
    ABORTED = "ABORTED"
    FAILED = "FAILED"


class RuntimeCanaryDecision(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class RuntimeCanaryDiagnosticSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class RuntimeCanaryScope(_RuntimeCanaryModel):
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


class RuntimeCanarySession(_RuntimeCanaryModel):
    session_id: str = Field(min_length=1, max_length=120)
    organization_id: str = Field(min_length=1, max_length=120)
    operational_unit_id: str = Field(min_length=1, max_length=120)
    planning_date: date
    timezone: str = Field(min_length=1, max_length=120)
    started_at: datetime
    ended_at: datetime | None = None
    status: RuntimeCanaryStatus = RuntimeCanaryStatus.CREATED
    authority_decision: str = Field(min_length=1, max_length=120)
    publication_id: str = Field(min_length=1, max_length=120)
    publication_version: int = Field(ge=1)

    _validate_started_at = field_validator("started_at")(_timezone_aware)

    @field_validator("ended_at")
    @classmethod
    def validate_ended_at(cls, value):
        return _timezone_aware(value) if value is not None else value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA identifier.") from exc
        return value

    @model_validator(mode="after")
    def validate_lifecycle(self):
        terminal = self.status in {
            RuntimeCanaryStatus.FINISHED,
            RuntimeCanaryStatus.ABORTED,
            RuntimeCanaryStatus.FAILED,
        }
        if terminal != (self.ended_at is not None):
            raise ValueError("Only terminal Canary sessions require ended_at.")
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("ended_at cannot precede started_at.")
        return self

    @property
    def scope(self) -> RuntimeCanaryScope:
        return RuntimeCanaryScope(
            organization_id=self.organization_id,
            operational_unit_id=self.operational_unit_id,
            planning_date=self.planning_date,
            timezone=self.timezone,
        )


class RuntimeCanaryPolicy(_RuntimeCanaryModel):
    minimum_parity_percent: float = Field(default=99.5, ge=0, le=100)
    maximum_critical_mismatch: int = Field(default=0, ge=0)
    maximum_duplicate_execution: int = Field(default=0, ge=0)
    maximum_authority_conflict: int = Field(default=0, ge=0)
    maximum_canary_overhead_percent: float = Field(default=5.0, ge=0)


class RuntimeCanaryMetrics(_RuntimeCanaryModel):
    parity_percent: float = Field(ge=0, le=100)
    critical_mismatch: int = Field(ge=0)
    high_mismatch: int = Field(ge=0)
    medium_mismatch: int = Field(ge=0)
    low_mismatch: int = Field(ge=0)
    duplicate_execution: int = Field(ge=0)
    authority_conflict: int = Field(ge=0)
    shadow_latency_ms: float = Field(ge=0)
    producer_latency_ms: float = Field(ge=0)
    comparator_latency_ms: float = Field(ge=0)
    canary_overhead_percent: float | None = Field(default=None, ge=0)


class RuntimeCanaryDiagnostic(_RuntimeCanaryModel):
    code: str = Field(min_length=1, max_length=120)
    severity: RuntimeCanaryDiagnosticSeverity
    message: str = Field(min_length=1, max_length=500)


class RuntimeCanaryDiagnostics(_RuntimeCanaryModel):
    items: tuple[RuntimeCanaryDiagnostic, ...] = Field(
        default_factory=tuple,
        max_length=100,
    )
    generated_at: datetime

    _validate_generated_at = field_validator("generated_at")(
        _timezone_aware
    )


class RuntimeCanaryCriterion(_RuntimeCanaryModel):
    code: str = Field(min_length=1, max_length=120)
    passed: bool
    actual: str = Field(min_length=1, max_length=120)
    expected: str = Field(min_length=1, max_length=120)


class RuntimeCanaryReport(_RuntimeCanaryModel):
    summary: str = Field(min_length=1, max_length=500)
    metrics: RuntimeCanaryMetrics
    mismatches: tuple[PlanningMismatch, ...] = Field(
        default_factory=tuple,
        max_length=100,
    )
    diagnostics: RuntimeCanaryDiagnostics
    duration_ms: float = Field(ge=0)
    decision: RuntimeCanaryDecision
    criteria: tuple[RuntimeCanaryCriterion, ...] = Field(
        min_length=1,
        max_length=20,
    )
    generated_at: datetime

    _validate_generated_at = field_validator("generated_at")(
        _timezone_aware
    )

    @model_validator(mode="after")
    def validate_decision(self):
        expected = (
            RuntimeCanaryDecision.PASS
            if all(item.passed for item in self.criteria)
            else RuntimeCanaryDecision.FAIL
        )
        if self.decision is not expected:
            raise ValueError("Canary decision must reflect every criterion.")
        return self


class RuntimeCanaryResult(_RuntimeCanaryModel):
    session: RuntimeCanarySession
    report: RuntimeCanaryReport
    status_history: tuple[RuntimeCanaryStatus, ...] = Field(
        min_length=3,
        max_length=6,
    )

    @model_validator(mode="after")
    def validate_history(self):
        if self.status_history[0] is not RuntimeCanaryStatus.CREATED:
            raise ValueError("Canary history must start with CREATED.")
        if self.status_history[-1] is not self.session.status:
            raise ValueError("Canary history must end with session status.")
        return self


class RuntimeCanaryEvaluationContext(_RuntimeCanaryModel):
    session: RuntimeCanarySession
    authority: AuthorityResolutionResult
    intent: ExecutionIntent
    attempt: ExecutionAttempt | None
    publication: ExecutionPublicationReference
    producer_result: PlanningRuntimeProducerResult | None = None
    shadow_result: RuntimeShadowResult | None = None
    producer_available: bool = True
    comparator_available: bool = True
    parity_engine_available: bool = True
    legacy_latency_ms: float | None = Field(default=None, gt=0)
