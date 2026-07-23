from datetime import datetime
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.domain.runtime_primary import (
    RuntimeCertificationGateStatus,
    RuntimeCertificationLevel,
    RuntimeCertificationSnapshot,
    RuntimePrimaryStatus,
)


class _LegacyRetirementModel(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)


def _timezone_aware(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("A timezone-aware datetime is required.")
    return value


class LegacyRetirementState(str, Enum):
    ACTIVE = "ACTIVE"
    STANDBY = "STANDBY"
    READY_FOR_RETIREMENT = "READY_FOR_RETIREMENT"
    BLOCKED = "BLOCKED"
    RETIRED = "RETIRED"


class LegacyRetirementDiagnosticSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class LegacyRetirementBlockerSeverity(str, Enum):
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class LegacyRetirementScope(_LegacyRetirementModel):
    organization_id: str = Field(min_length=1, max_length=120)


class LegacyRetirementPolicy(_LegacyRetirementModel):
    required_certification_level: RuntimeCertificationLevel = (
        RuntimeCertificationLevel.LEVEL_3
    )
    required_gate_codes: tuple[str, ...] = tuple(
        f"GATE_{index}" for index in range(1, 11)
    )
    minimum_runtime_stable_days: int = Field(default=30, ge=30)
    minimum_runtime_execution_count: int = Field(default=500, ge=500)
    minimum_runtime_success_percent: float = Field(
        default=99.9,
        ge=99.9,
        le=100,
    )
    maximum_critical_mismatch: int = Field(default=0, ge=0)
    maximum_duplicate_execution: int = Field(default=0, ge=0)
    maximum_sev1_incidents: int = Field(default=0, ge=0)
    maximum_sev2_incidents: int = Field(default=0, ge=0)


class LegacyRetirementBlocker(_LegacyRetirementModel):
    code: str = Field(min_length=1, max_length=120)
    severity: LegacyRetirementBlockerSeverity
    message: str = Field(min_length=1, max_length=300)


class LegacyRetirementContext(_LegacyRetirementModel):
    scope: LegacyRetirementScope
    observed_state: LegacyRetirementState
    runtime_primary_status: RuntimePrimaryStatus
    certification: RuntimeCertificationSnapshot
    open_blockers: tuple[LegacyRetirementBlocker, ...] = Field(
        default_factory=tuple,
        max_length=100,
    )
    critical_mismatch_count: int = Field(ge=0)
    duplicate_execution_count: int = Field(ge=0)
    rollback_verified: bool
    rollback_available: bool
    audit_complete: bool
    canary_complete: bool
    runtime_primary_stable: bool
    runtime_stable_days: int = Field(ge=0)
    runtime_execution_count: int = Field(ge=0)
    runtime_success_percent: float = Field(ge=0, le=100)
    all_operational_units_enabled: bool
    sev1_incident_count: int = Field(ge=0)
    sev2_incident_count: int = Field(ge=0)
    legacy_available: bool
    legacy_observable: bool
    legacy_recoverable: bool
    legacy_code_present: bool
    evaluated_at: datetime

    _validate_evaluated_at = field_validator("evaluated_at")(
        _timezone_aware
    )

    @model_validator(mode="after")
    def validate_observed_state(self):
        if self.observed_state not in {
            LegacyRetirementState.ACTIVE,
            LegacyRetirementState.STANDBY,
        }:
            raise ValueError(
                "Observed Legacy state must be ACTIVE or STANDBY."
            )
        return self


class LegacyRetirementCheck(_LegacyRetirementModel):
    code: str = Field(min_length=1, max_length=120)
    passed: bool
    reason: str = Field(min_length=1, max_length=300)
    remediation_hint: str | None = Field(default=None, max_length=300)


class LegacyRetirementGateSummary(_LegacyRetirementModel):
    required_count: int = Field(ge=1)
    pass_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    fail_count: int = Field(ge=0)
    missing_codes: tuple[str, ...] = Field(
        default_factory=tuple,
        max_length=20,
    )
    status: RuntimeCertificationGateStatus

    @model_validator(mode="after")
    def validate_counts(self):
        if (
            self.pass_count + self.warning_count + self.fail_count
            > self.required_count
        ):
            raise ValueError("Gate counts exceed required gates.")
        return self


class LegacyRetirementValidationResult(_LegacyRetirementModel):
    allowed: bool
    checklist: tuple[LegacyRetirementCheck, ...] = Field(
        min_length=1,
        max_length=20,
    )
    gates: LegacyRetirementGateSummary
    evaluated_at: datetime

    _validate_evaluated_at = field_validator("evaluated_at")(
        _timezone_aware
    )

    @model_validator(mode="after")
    def validate_allowed(self):
        if self.allowed != all(item.passed for item in self.checklist):
            raise ValueError("Decision must reflect every checklist item.")
        return self


class LegacyRetirementDiagnostic(_LegacyRetirementModel):
    code: str = Field(min_length=1, max_length=120)
    severity: LegacyRetirementDiagnosticSeverity
    message: str = Field(min_length=1, max_length=300)
    remediation_hint: str | None = Field(default=None, max_length=300)


class LegacyRetirementDiagnostics(_LegacyRetirementModel):
    items: tuple[LegacyRetirementDiagnostic, ...] = Field(
        default_factory=tuple,
        max_length=20,
    )
    generated_at: datetime

    _validate_generated_at = field_validator("generated_at")(
        _timezone_aware
    )


class LegacyRetirementMetrics(_LegacyRetirementModel):
    legacy_active: bool
    legacy_standby: bool
    legacy_available: bool
    legacy_observable: bool
    legacy_recoverable: bool
    runtime_readiness: bool
    certification_level: RuntimeCertificationLevel
    gate_status: RuntimeCertificationGateStatus
    rollback_available: bool
    runtime_stable_days: int = Field(ge=0)
    runtime_execution_count: int = Field(ge=0)
    runtime_success_percent: float = Field(ge=0, le=100)
    validation_latency_ms: float = Field(ge=0)


class LegacyRetirementReport(_LegacyRetirementModel):
    scope: LegacyRetirementScope
    state: LegacyRetirementState
    reason: str = Field(min_length=1, max_length=500)
    checklist: tuple[LegacyRetirementCheck, ...] = Field(
        min_length=1,
        max_length=20,
    )
    gates: LegacyRetirementGateSummary
    blockers: tuple[LegacyRetirementBlocker, ...] = Field(
        default_factory=tuple,
        max_length=100,
    )
    metrics: LegacyRetirementMetrics
    diagnostics: LegacyRetirementDiagnostics
    duration_ms: float = Field(ge=0)
    generated_at: datetime

    _validate_generated_at = field_validator("generated_at")(
        _timezone_aware
    )

    @model_validator(mode="after")
    def validate_state(self):
        ready = all(item.passed for item in self.checklist)
        if self.state is LegacyRetirementState.READY_FOR_RETIREMENT:
            if not ready:
                raise ValueError("READY_FOR_RETIREMENT requires all checks.")
        if self.state is LegacyRetirementState.BLOCKED and ready:
            raise ValueError("BLOCKED requires at least one failed check.")
        return self
