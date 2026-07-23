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

from app.domain.runtime_authority import AuthorityDecisionId


class _ExecutionIntentModel(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)


class ExecutionIntentId(RootModel[str]):
    root: str = Field(min_length=1, max_length=120)
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    def __str__(self) -> str:
        return self.root


class ExecutionIntentKey(RootModel[str]):
    root: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return self.root


class ExecutionIntentVersion(RootModel[int]):
    root: int = Field(ge=1)
    model_config = ConfigDict(frozen=True)

    def __int__(self) -> int:
        return self.root


class ExecutionIntentStatus(str, Enum):
    CREATED = "CREATED"
    READY = "READY"
    LOCKED = "LOCKED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"
    REJECTED = "REJECTED"


class ExecutionIntentMode(str, Enum):
    NORMAL = "NORMAL"
    SHADOW = "SHADOW"
    VERIFY = "VERIFY"
    ROLLBACK = "ROLLBACK"


class ExecutionPublicationStatus(str, Enum):
    PUBLISHED = "PUBLISHED"
    SUPERSEDED = "SUPERSEDED"
    REVOKED = "REVOKED"


class ExecutionIntentDiagnosticSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


def _timezone_aware(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("A timezone-aware datetime is required.")
    return value


class ExecutionIntentScope(_ExecutionIntentModel):
    organization_id: str = Field(min_length=1, max_length=120)
    operational_unit_id: str = Field(min_length=1, max_length=120)
    planning_date: date
    timezone: str = Field(min_length=1, max_length=120)
    publication_id: str = Field(min_length=1, max_length=120)
    publication_version: int = Field(ge=1)
    execution_mode: ExecutionIntentMode

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA identifier.") from exc
        return value

    @property
    def operational_identity(self) -> tuple[str, str, date, str]:
        return (
            self.organization_id,
            self.operational_unit_id,
            self.planning_date,
            self.timezone,
        )

    @property
    def identity(self) -> tuple[str, str, date, str, str, int, str]:
        return (
            *self.operational_identity,
            self.publication_id,
            self.publication_version,
            self.execution_mode.value,
        )


class ExecutionAttemptReference(_ExecutionIntentModel):
    attempt_id: str = Field(min_length=1, max_length=120)
    attempt_version: int = Field(ge=1)


class ExecutionPublicationReference(_ExecutionIntentModel):
    organization_id: str = Field(min_length=1, max_length=120)
    operational_unit_id: str = Field(min_length=1, max_length=120)
    planning_date: date
    publication_id: str = Field(min_length=1, max_length=120)
    publication_version: int = Field(ge=1)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: ExecutionPublicationStatus


class ExecutionIntentCommand(_ExecutionIntentModel):
    scope: ExecutionIntentScope
    publication_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=8, max_length=160)
    expected_version: int = Field(ge=0)
    authority_decision_id: AuthorityDecisionId
    fencing_token: int = Field(ge=1)
    actor: str = Field(min_length=1, max_length=120)


class ExecutionIntent(_ExecutionIntentModel):
    intent_id: ExecutionIntentId
    intent_key: ExecutionIntentKey
    scope: ExecutionIntentScope
    version: ExecutionIntentVersion
    status: ExecutionIntentStatus
    publication_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_decision_id: AuthorityDecisionId
    fencing_token: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=160)
    payload_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    actor: str = Field(min_length=1, max_length=120)
    created_at: datetime
    attempt_reference: ExecutionAttemptReference | None = None

    _validate_created_at = field_validator("created_at")(_timezone_aware)


class ExecutionIntentValidationRule(_ExecutionIntentModel):
    code: str = Field(min_length=1, max_length=120)
    passed: bool
    reason: str = Field(min_length=1, max_length=500)
    remediation_hint: str = Field(min_length=1, max_length=500)


class ExecutionIntentValidationResult(_ExecutionIntentModel):
    status: ExecutionIntentStatus
    allowed: bool
    rules: tuple[ExecutionIntentValidationRule, ...] = Field(
        min_length=1,
        max_length=20,
    )
    evaluated_at: datetime

    _validate_evaluated_at = field_validator("evaluated_at")(_timezone_aware)

    @model_validator(mode="after")
    def validate_result(self):
        all_passed = all(rule.passed for rule in self.rules)
        if self.allowed:
            if self.status is not ExecutionIntentStatus.READY or not all_passed:
                raise ValueError("Allowed validation must be READY and pass all rules.")
        elif self.status is not ExecutionIntentStatus.REJECTED or all_passed:
            raise ValueError("Rejected validation requires at least one failed rule.")
        return self


class ExecutionIntentDiagnostic(_ExecutionIntentModel):
    code: str = Field(min_length=1, max_length=120)
    severity: ExecutionIntentDiagnosticSeverity
    message: str = Field(min_length=1, max_length=500)


class ExecutionIntentDiagnostics(_ExecutionIntentModel):
    items: tuple[ExecutionIntentDiagnostic, ...] = Field(
        default_factory=tuple,
        max_length=12,
    )
    generated_at: datetime

    _validate_generated_at = field_validator("generated_at")(_timezone_aware)


class ExecutionIntentCreationResult(_ExecutionIntentModel):
    status: ExecutionIntentStatus
    intent: ExecutionIntent | None = None
    validation: ExecutionIntentValidationResult
    diagnostics: ExecutionIntentDiagnostics
    idempotent: bool = False
    generated_at: datetime

    _validate_generated_at = field_validator("generated_at")(_timezone_aware)

    @model_validator(mode="after")
    def validate_creation(self):
        if self.status is ExecutionIntentStatus.READY and self.intent is None:
            raise ValueError("READY creation requires an ExecutionIntent.")
        if self.status is ExecutionIntentStatus.REJECTED and self.intent is not None:
            raise ValueError("REJECTED creation cannot return a new intent.")
        return self


class ExecutionIntentRuntimeReport(_ExecutionIntentModel):
    intent: ExecutionIntent | None = None
    diagnostics: ExecutionIntentDiagnostics
    generated_at: datetime

    _validate_generated_at = field_validator("generated_at")(_timezone_aware)
