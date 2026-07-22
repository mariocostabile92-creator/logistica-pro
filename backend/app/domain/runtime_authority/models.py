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


class _AuthorityModel(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)


class AuthorityDecisionId(RootModel[str]):
    root: str = Field(min_length=1, max_length=120)
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    def __str__(self) -> str:
        return self.root


class AuthorityDecisionVersion(RootModel[int]):
    root: int = Field(ge=1)
    model_config = ConfigDict(frozen=True)

    def __int__(self) -> int:
        return self.root


class AuthorityDecisionMode(str, Enum):
    LEGACY = "LEGACY"
    RUNTIME = "RUNTIME"
    SHADOW = "SHADOW"
    VERIFY = "VERIFY"
    ROLLBACK_LOCKED = "ROLLBACK_LOCKED"
    DISABLED = "DISABLED"


class AuthorityStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"
    INVALID = "INVALID"
    REVOKED = "REVOKED"


class AuthorityResolutionState(str, Enum):
    WRITE_ALLOWED = "WRITE_ALLOWED"
    NO_WRITE = "NO_WRITE"


class AuthorityDiagnosticSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


def _timezone_aware(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("A timezone-aware datetime is required.")
    return value


class AuthorityScope(_AuthorityModel):
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


class AuthorityDecision(_AuthorityModel):
    decision_id: AuthorityDecisionId
    scope: AuthorityScope
    mode: AuthorityDecisionMode
    status: AuthorityStatus = AuthorityStatus.ACTIVE
    priority: int = Field(ge=0, le=100)
    version: AuthorityDecisionVersion
    valid_from: datetime
    valid_until: datetime
    reason: str = Field(min_length=1, max_length=500)
    actor: str = Field(min_length=1, max_length=120)
    created_at: datetime
    fencing_token: int = Field(ge=1)

    _validate_valid_from = field_validator("valid_from")(_timezone_aware)
    _validate_valid_until = field_validator("valid_until")(_timezone_aware)
    _validate_created_at = field_validator("created_at")(_timezone_aware)

    @model_validator(mode="after")
    def validate_interval(self):
        if self.valid_until <= self.valid_from:
            raise ValueError("valid_until must be later than valid_from.")
        return self


class AuthorityConflict(_AuthorityModel):
    code: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=500)
    decision_ids: tuple[AuthorityDecisionId, ...] = Field(
        min_length=2,
        max_length=20,
    )
    priorities: tuple[int, ...] = Field(min_length=2, max_length=20)
    versions: tuple[int, ...] = Field(min_length=2, max_length=20)
    fencing_tokens: tuple[int, ...] = Field(min_length=2, max_length=20)

    @model_validator(mode="after")
    def validate_dimensions(self):
        expected = len(self.decision_ids)
        if not all(
            len(values) == expected
            for values in (
                self.priorities,
                self.versions,
                self.fencing_tokens,
            )
        ):
            raise ValueError("Conflict dimensions must have the same length.")
        return self


class AuthorityResolutionResult(_AuthorityModel):
    state: AuthorityResolutionState
    scope: AuthorityScope
    decision: AuthorityDecision | None = None
    reason_code: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=500)
    conflicts: tuple[AuthorityConflict, ...] = Field(
        default_factory=tuple,
        max_length=5,
    )
    assessed_at: datetime

    _validate_assessed_at = field_validator("assessed_at")(_timezone_aware)

    @model_validator(mode="after")
    def validate_resolution(self):
        if self.state is AuthorityResolutionState.WRITE_ALLOWED:
            if self.decision is None:
                raise ValueError("WRITE_ALLOWED requires an AuthorityDecision.")
            if self.decision.mode not in {
                AuthorityDecisionMode.LEGACY,
                AuthorityDecisionMode.RUNTIME,
            }:
                raise ValueError("The selected mode cannot authorize writes.")
            if self.conflicts:
                raise ValueError("A conflicting resolution cannot allow writes.")
        return self


class AuthorityDiagnostic(_AuthorityModel):
    code: str = Field(min_length=1, max_length=120)
    severity: AuthorityDiagnosticSeverity
    message: str = Field(min_length=1, max_length=500)


class AuthorityDiagnostics(_AuthorityModel):
    items: tuple[AuthorityDiagnostic, ...] = Field(
        default_factory=tuple,
        max_length=10,
    )
    generated_at: datetime

    _validate_generated_at = field_validator("generated_at")(_timezone_aware)
