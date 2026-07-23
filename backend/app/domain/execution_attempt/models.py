from datetime import date, datetime
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    field_validator,
    model_validator,
)

from app.domain.execution_intent import ExecutionIntentId
from app.domain.runtime_authority import AuthorityDecisionId


class _ExecutionAttemptModel(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)


class ExecutionAttemptId(RootModel[str]):
    root: str = Field(min_length=1, max_length=120)
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    def __str__(self) -> str:
        return self.root


class ExecutionAttemptVersion(RootModel[int]):
    root: int = Field(ge=1)
    model_config = ConfigDict(frozen=True)

    def __int__(self) -> int:
        return self.root


class ExecutionAttemptStatus(str, Enum):
    PENDING = "PENDING"
    LOCK_ACQUIRED = "LOCK_ACQUIRED"
    READY_TO_EXECUTE = "READY_TO_EXECUTE"
    ABORTED = "ABORTED"
    REJECTED = "REJECTED"


class ExecutionAttemptMode(str, Enum):
    NORMAL = "NORMAL"
    SHADOW = "SHADOW"
    VERIFY = "VERIFY"


class LockState(str, Enum):
    AVAILABLE = "AVAILABLE"
    ACQUIRED = "ACQUIRED"
    UNAVAILABLE = "UNAVAILABLE"
    RELEASED = "RELEASED"


class LockToken(RootModel[str]):
    root: str = Field(min_length=16, max_length=160)
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    def __str__(self) -> str:
        return self.root


class LockOwner(RootModel[str]):
    root: str = Field(min_length=1, max_length=120)
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    def __str__(self) -> str:
        return self.root


class ExecutionAttemptDiagnosticSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


def _timezone_aware(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("A timezone-aware datetime is required.")
    return value


def _valid_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("timezone must be a valid IANA identifier.") from exc
    return value


class ExecutionAttemptSeriesScope(_ExecutionAttemptModel):
    organization_id: str = Field(min_length=1, max_length=120)
    operational_unit_id: str = Field(min_length=1, max_length=120)
    planning_date: date
    timezone: str = Field(min_length=1, max_length=120)
    execution_intent_id: ExecutionIntentId

    _validate_timezone = field_validator("timezone")(_valid_timezone)

    @property
    def identity(self) -> tuple[str, str, date, str, str]:
        return (
            self.organization_id,
            self.operational_unit_id,
            self.planning_date,
            self.timezone,
            str(self.execution_intent_id),
        )


class ExecutionAttemptScope(ExecutionAttemptSeriesScope):
    attempt_number: int = Field(ge=1)

    @property
    def identity(self) -> tuple[str, str, date, str, str, int]:
        return (*super().identity, self.attempt_number)

    @property
    def series_scope(self) -> ExecutionAttemptSeriesScope:
        return ExecutionAttemptSeriesScope(
            organization_id=self.organization_id,
            operational_unit_id=self.operational_unit_id,
            planning_date=self.planning_date,
            timezone=self.timezone,
            execution_intent_id=self.execution_intent_id,
        )


class LockDiagnostic(_ExecutionAttemptModel):
    code: str = Field(min_length=1, max_length=120)
    severity: ExecutionAttemptDiagnosticSeverity
    message: str = Field(min_length=1, max_length=500)


class LockDiagnostics(_ExecutionAttemptModel):
    state: LockState
    items: tuple[LockDiagnostic, ...] = Field(
        default_factory=tuple,
        max_length=10,
    )
    generated_at: datetime

    _validate_generated_at = field_validator("generated_at")(_timezone_aware)


class ExecutionAttemptCommand(_ExecutionAttemptModel):
    series_scope: ExecutionAttemptSeriesScope
    expected_intent_version: int = Field(ge=1)
    authority_decision_id: AuthorityDecisionId
    fencing_token: int = Field(ge=1)
    actor: str = Field(min_length=1, max_length=120)


class ExecutionAttempt(_ExecutionAttemptModel):
    attempt_id: ExecutionAttemptId
    scope: ExecutionAttemptScope
    mode: ExecutionAttemptMode
    version: ExecutionAttemptVersion
    status: ExecutionAttemptStatus
    intent_version: int = Field(ge=1)
    publication_id: str = Field(min_length=1, max_length=120)
    publication_version: int = Field(ge=1)
    publication_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_decision_id: AuthorityDecisionId
    fencing_token: int = Field(ge=1)
    actor: str = Field(min_length=1, max_length=120)
    created_at: datetime
    lock_state: LockState = LockState.AVAILABLE
    lock_token: LockToken | None = None
    lock_owner: LockOwner | None = None
    lock_diagnostics: LockDiagnostics

    _validate_created_at = field_validator("created_at")(_timezone_aware)

    @model_validator(mode="after")
    def validate_lock(self):
        if self.lock_state is LockState.ACQUIRED:
            if self.lock_token is None or self.lock_owner is None:
                raise ValueError("ACQUIRED lock requires token and owner.")
        elif self.lock_token is not None or self.lock_owner is not None:
            raise ValueError("Only ACQUIRED lock can expose token and owner.")
        if self.lock_diagnostics.state is not self.lock_state:
            raise ValueError("Lock diagnostics must match lock state.")
        return self


class ExecutionAttemptHistory(_ExecutionAttemptModel):
    scope: ExecutionAttemptSeriesScope
    total: int = Field(ge=0)
    attempts: tuple[ExecutionAttempt, ...] = Field(
        default_factory=tuple,
        max_length=100,
    )

    @model_validator(mode="after")
    def validate_history(self):
        if self.total < len(self.attempts):
            raise ValueError("History total cannot be smaller than its page.")
        if any(
            attempt.scope.series_scope.identity != self.scope.identity
            for attempt in self.attempts
        ):
            raise ValueError("Every attempt must share the history scope.")
        return self


class ExecutionAttemptValidationRule(_ExecutionAttemptModel):
    code: str = Field(min_length=1, max_length=120)
    passed: bool
    reason: str = Field(min_length=1, max_length=500)
    remediation_hint: str = Field(min_length=1, max_length=500)


class ExecutionAttemptValidationResult(_ExecutionAttemptModel):
    status: ExecutionAttemptStatus
    allowed: bool
    rules: tuple[ExecutionAttemptValidationRule, ...] = Field(
        min_length=1,
        max_length=20,
    )
    evaluated_at: datetime

    _validate_evaluated_at = field_validator("evaluated_at")(_timezone_aware)

    @model_validator(mode="after")
    def validate_result(self):
        all_passed = all(rule.passed for rule in self.rules)
        if self.allowed:
            if self.status is not ExecutionAttemptStatus.PENDING or not all_passed:
                raise ValueError("Allowed validation must be PENDING and pass.")
        elif self.status is not ExecutionAttemptStatus.REJECTED or all_passed:
            raise ValueError("Rejected validation requires a failed rule.")
        return self


class ExecutionAttemptDiagnostic(_ExecutionAttemptModel):
    code: str = Field(min_length=1, max_length=120)
    severity: ExecutionAttemptDiagnosticSeverity
    message: str = Field(min_length=1, max_length=500)


class ExecutionAttemptDiagnostics(_ExecutionAttemptModel):
    items: tuple[ExecutionAttemptDiagnostic, ...] = Field(
        default_factory=tuple,
        max_length=12,
    )
    generated_at: datetime

    _validate_generated_at = field_validator("generated_at")(_timezone_aware)


class ExecutionAttemptCreationResult(_ExecutionAttemptModel):
    status: ExecutionAttemptStatus
    attempt: ExecutionAttempt | None = None
    validation: ExecutionAttemptValidationResult
    diagnostics: ExecutionAttemptDiagnostics
    generated_at: datetime

    _validate_generated_at = field_validator("generated_at")(_timezone_aware)

    @model_validator(mode="after")
    def validate_creation(self):
        if self.status is ExecutionAttemptStatus.PENDING and self.attempt is None:
            raise ValueError("PENDING creation requires an attempt.")
        if self.status is ExecutionAttemptStatus.REJECTED and self.attempt is not None:
            raise ValueError("REJECTED creation cannot return an attempt.")
        return self


class ExecutionAttemptRuntimeReport(_ExecutionAttemptModel):
    attempt: ExecutionAttempt | None = None
    diagnostics: ExecutionAttemptDiagnostics
    generated_at: datetime

    _validate_generated_at = field_validator("generated_at")(_timezone_aware)
