from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.core_language import OperationalUnit
from app.domain.planning_inputs import PlanningInputEnvelope, PlanningInputSnapshot


class _ReadinessModel(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)


def _require_timezone(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("A timezone-aware datetime is required.")
    return value


class PlanningReadinessStatus(str, Enum):
    READY = "READY"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"
    STALE = "STALE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    INVALID = "INVALID"
    INCOMPATIBLE = "INCOMPATIBLE"
    LEGACY = "LEGACY"


class PlanningReadinessSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class PlanningReadinessRule(_ReadinessModel):
    code: str = Field(min_length=1)
    category: str = Field(min_length=1)
    description: str = Field(min_length=1)
    source: str = Field(min_length=1)
    weight: int = Field(ge=0, le=100)
    blocking: bool
    failure_message: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    remediation_hint: str = Field(min_length=1)


class PlanningReadinessRuleResult(_ReadinessModel):
    code: str = Field(min_length=1)
    category: str = Field(min_length=1)
    passed: bool | None
    weight: int = Field(ge=0, le=100)
    score_awarded: int = Field(ge=0, le=100)
    blocking: bool
    message: str = Field(min_length=1)
    source: str = Field(min_length=1)
    severity: PlanningReadinessSeverity


class _PlanningReadinessIssue(_ReadinessModel):
    code: str = Field(min_length=1)
    category: str = Field(min_length=1)
    message: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    source: str = Field(min_length=1)
    severity: PlanningReadinessSeverity
    remediation_hint: str = Field(min_length=1)


class PlanningReadinessBlocker(_PlanningReadinessIssue):
    severity: PlanningReadinessSeverity = PlanningReadinessSeverity.CRITICAL


class PlanningReadinessWarning(_PlanningReadinessIssue):
    severity: PlanningReadinessSeverity = PlanningReadinessSeverity.WARNING


class PlanningReadinessMissingInput(_PlanningReadinessIssue):
    input_name: str = Field(min_length=1)


class PlanningReadinessDiagnostic(_PlanningReadinessIssue):
    pass


class PlanningReadinessScore(_ReadinessModel):
    value: int = Field(ge=0, le=100)
    earned_weight: int = Field(ge=0, le=100)
    total_weight: int = Field(default=100, ge=1, le=100)

    @model_validator(mode="after")
    def validate_score(self):
        expected = round((self.earned_weight / self.total_weight) * 100)
        if self.value != expected:
            raise ValueError("Score value must reflect the awarded rule weights.")
        return self


class PlanningReadinessCompatibilityCheck(_ReadinessModel):
    code: str = Field(min_length=1)
    compatible: bool | None
    message: str = Field(min_length=1)


class PlanningReadinessEvaluationReport(_ReadinessModel):
    runtime_status: str = Field(min_length=1)
    envelope: PlanningInputEnvelope | None = None
    workforce: PlanningInputSnapshot | None = None
    fleet: PlanningInputSnapshot | None = None
    expected_operational_unit: OperationalUnit
    expected_planning_date: date
    compatibility_checks: tuple[
        PlanningReadinessCompatibilityCheck, ...
    ] = Field(default_factory=tuple)
    runtime_warnings: tuple[str, ...] = Field(default_factory=tuple)
    runtime_errors: tuple[str, ...] = Field(default_factory=tuple)
    runtime_reasons: tuple[str, ...] = Field(default_factory=tuple)
    evaluated_at: datetime
    legacy_flow_active: bool = True

    _validate_evaluated_at = field_validator("evaluated_at")(
        _require_timezone
    )


class PlanningReadinessResult(_ReadinessModel):
    status: PlanningReadinessStatus
    score: PlanningReadinessScore
    is_ready: bool
    blockers: tuple[PlanningReadinessBlocker, ...] = Field(
        default_factory=tuple
    )
    warnings: tuple[PlanningReadinessWarning, ...] = Field(
        default_factory=tuple
    )
    missing_inputs: tuple[PlanningReadinessMissingInput, ...] = Field(
        default_factory=tuple
    )
    diagnostics: tuple[PlanningReadinessDiagnostic, ...] = Field(
        default_factory=tuple
    )
    evaluated_at: datetime
    operational_unit: OperationalUnit
    planning_date: date
    envelope_version: str | None = None
    envelope_fingerprint: str | None = None
    rule_results: tuple[PlanningReadinessRuleResult, ...] = Field(
        default_factory=tuple
    )
    rationale: str = Field(min_length=1)
    legacy_flow_active: bool = True

    _validate_evaluated_at = field_validator("evaluated_at")(
        _require_timezone
    )

    @model_validator(mode="after")
    def validate_ready_flag(self):
        expected = self.status in {
            PlanningReadinessStatus.READY,
            PlanningReadinessStatus.WARNING,
        }
        if self.is_ready != expected:
            raise ValueError("is_ready must reflect the readiness status.")
        if self.is_ready and self.blockers:
            raise ValueError("A ready result cannot contain blockers.")
        return self
