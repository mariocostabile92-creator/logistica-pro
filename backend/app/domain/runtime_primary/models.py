from datetime import datetime
from enum import Enum

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
from app.domain.planning_runtime import (
    PlanningRuntimeProducerResult,
    PlanningRuntimeScope,
)
from app.domain.runtime_authority import AuthorityResolutionResult
from app.domain.runtime_canary import RuntimeCanaryResult
from app.domain.runtime_shadow import RuntimeShadowResult


class _RuntimePrimaryModel(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)


def _timezone_aware(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("A timezone-aware datetime is required.")
    return value


class RuntimePrimaryMode(str, Enum):
    CANARY = "CANARY"
    PRIMARY = "PRIMARY"
    ROLLBACK = "ROLLBACK"
    DISABLED = "DISABLED"


class RuntimePrimaryStatus(str, Enum):
    DISABLED = "DISABLED"
    CANARY = "CANARY"
    READY_TO_PROMOTE = "READY_TO_PROMOTE"
    READY_TO_ROLLBACK = "READY_TO_ROLLBACK"
    PRIMARY = "PRIMARY"
    ROLLED_BACK = "ROLLED_BACK"
    REJECTED = "REJECTED"
    ERROR = "ERROR"


class RuntimePrimaryDecision(str, Enum):
    DENY = "DENY"
    OBSERVE = "OBSERVE"
    ELIGIBLE = "ELIGIBLE"
    PROMOTED = "PROMOTED"
    FALLBACK = "FALLBACK"


class RuntimePrimaryOutcome(str, Enum):
    NO_EFFECT = "NO_EFFECT"
    RUNTIME_WRITE_COMMITTED = "RUNTIME_WRITE_COMMITTED"
    LEGACY_FALLBACK_ACTIVATED = "LEGACY_FALLBACK_ACTIVATED"
    FAILED_CLOSED = "FAILED_CLOSED"
    ERROR = "ERROR"


class RuntimePrimaryDiagnosticSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class RuntimeCertificationLevel(str, Enum):
    LEVEL_0 = "LEVEL_0"
    LEVEL_1 = "LEVEL_1"
    LEVEL_2 = "LEVEL_2"
    LEVEL_3 = "LEVEL_3"
    LEVEL_4 = "LEVEL_4"

    @property
    def rank(self) -> int:
        return int(self.value[-1])


class RuntimeCertificationDecision(str, Enum):
    GO = "GO"
    NO_GO = "NO_GO"


class RuntimeCertificationGateStatus(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class RuntimeCertificationGate(_RuntimePrimaryModel):
    code: str = Field(pattern=r"^GATE_(10|[1-9])$")
    status: RuntimeCertificationGateStatus
    evidence_reference: str = Field(min_length=1, max_length=240)


class RuntimeCertificationSnapshot(_RuntimePrimaryModel):
    level: RuntimeCertificationLevel
    decision: RuntimeCertificationDecision
    gates: tuple[RuntimeCertificationGate, ...] = Field(
        min_length=1,
        max_length=20,
    )
    certified_at: datetime
    record_reference: str = Field(min_length=1, max_length=240)

    _validate_certified_at = field_validator("certified_at")(
        _timezone_aware
    )

    @model_validator(mode="after")
    def validate_unique_gates(self):
        codes = tuple(gate.code for gate in self.gates)
        if len(codes) != len(set(codes)):
            raise ValueError("Certification gate codes must be unique.")
        all_passed = all(
            gate.status is RuntimeCertificationGateStatus.PASS
            for gate in self.gates
        )
        if (
            self.decision is RuntimeCertificationDecision.GO
        ) != all_passed:
            raise ValueError(
                "Certification decision must reflect all supplied gates."
            )
        return self


class RuntimePrimaryCohort(_RuntimePrimaryModel):
    cohort_id: str = Field(min_length=1, max_length=120)
    organization_id: str = Field(min_length=1, max_length=120)
    operational_unit_ids: tuple[str, ...] = Field(
        min_length=1,
        max_length=20,
    )
    execution_percentage: float = Field(gt=0, le=100)
    feature_flag_key: str = Field(min_length=1, max_length=160)
    feature_flag_version: str = Field(min_length=1, max_length=120)
    enabled: bool
    selected_for_execution: bool


class RuntimePrimaryCohortEvidence(_RuntimePrimaryModel):
    observed_operational_days: int = Field(ge=0)
    observed_execution_count: int = Field(ge=0)
    execution_success_percent: float = Field(ge=0, le=100)
    sev1_incident_count: int = Field(ge=0)
    sev2_incident_count: int = Field(ge=0)
    mixed_version_deploy_passed: bool


class RuntimePrimaryPolicy(_RuntimePrimaryModel):
    minimum_parity_percent: float = Field(default=99.5, ge=0, le=100)
    maximum_critical_mismatch: int = Field(default=0, ge=0)
    maximum_duplicate_execution: int = Field(default=0, ge=0)
    maximum_operational_units: int = Field(default=1, ge=1, le=1)
    maximum_execution_percentage: float = Field(default=5.0, gt=0, le=5)
    minimum_observed_operational_days: int = Field(default=14, ge=1)
    minimum_observed_execution_count: int = Field(default=500, ge=1)
    minimum_execution_success_percent: float = Field(
        default=99.9,
        ge=0,
        le=100,
    )
    maximum_sev1_incident_count: int = Field(default=0, ge=0)
    maximum_sev2_incident_count: int = Field(default=0, ge=0)
    required_certification_level: RuntimeCertificationLevel = (
        RuntimeCertificationLevel.LEVEL_2
    )
    required_gate_codes: tuple[str, ...] = tuple(
        f"GATE_{index}" for index in range(1, 11)
    )
    require_canary_pass: bool = True
    require_comparator: bool = True
    require_runtime_output: bool = True
    require_legacy_standby: bool = True


class RuntimePrimaryEvaluationContext(_RuntimePrimaryModel):
    scope: PlanningRuntimeScope
    requested_mode: RuntimePrimaryMode
    authority: AuthorityResolutionResult
    publication: ExecutionPublicationReference
    intent: ExecutionIntent
    attempt: ExecutionAttempt | None = None
    canary: RuntimeCanaryResult | None = None
    comparator: RuntimeShadowResult | None = None
    runtime_output: PlanningRuntimeProducerResult | None = None
    certification: RuntimeCertificationSnapshot
    cohort: RuntimePrimaryCohort
    cohort_evidence: RuntimePrimaryCohortEvidence
    legacy_available: bool = True
    legacy_write_active: bool = False
    runtime_write_active: bool = False
    active_execution: bool = False
    rollback_authorized: bool = False
    reconciliation_complete: bool = False
    state_preservation_verified: bool = False
    legacy_latency_ms: float | None = Field(default=None, gt=0)
    evaluated_at: datetime

    _validate_evaluated_at = field_validator("evaluated_at")(
        _timezone_aware
    )


class RuntimePrimaryValidationRule(_RuntimePrimaryModel):
    code: str = Field(min_length=1, max_length=120)
    passed: bool
    reason: str = Field(min_length=1, max_length=500)
    remediation_hint: str = Field(min_length=1, max_length=500)


class RuntimePrimaryValidationResult(_RuntimePrimaryModel):
    allowed: bool
    rules: tuple[RuntimePrimaryValidationRule, ...] = Field(
        min_length=1,
        max_length=40,
    )
    evaluated_at: datetime

    _validate_evaluated_at = field_validator("evaluated_at")(
        _timezone_aware
    )

    @model_validator(mode="after")
    def validate_allowed(self):
        all_passed = all(rule.passed for rule in self.rules)
        if self.allowed != all_passed:
            raise ValueError("Validation decision must reflect every rule.")
        return self


class RuntimePrimaryDiagnostic(_RuntimePrimaryModel):
    code: str = Field(min_length=1, max_length=120)
    severity: RuntimePrimaryDiagnosticSeverity
    message: str = Field(min_length=1, max_length=500)
    remediation_hint: str | None = Field(default=None, max_length=500)


class RuntimePrimaryDiagnostics(_RuntimePrimaryModel):
    items: tuple[RuntimePrimaryDiagnostic, ...] = Field(
        default_factory=tuple,
        max_length=50,
    )
    generated_at: datetime

    _validate_generated_at = field_validator("generated_at")(
        _timezone_aware
    )


class RuntimePrimaryWriteResult(_RuntimePrimaryModel):
    committed: bool
    runtime_write_count: int = Field(ge=0, le=1)
    duplicate_execution: int = Field(ge=0)
    latency_ms: float = Field(ge=0)
    outcome_reference: str = Field(min_length=1, max_length=240)
    fencing_token: int = Field(ge=1)


class LegacyFallbackResult(_RuntimePrimaryModel):
    activated: bool
    legacy_fallback_count: int = Field(ge=0, le=1)
    state_preserved: bool
    latency_ms: float = Field(ge=0)
    outcome_reference: str = Field(min_length=1, max_length=240)


class RuntimePrimaryMetrics(_RuntimePrimaryModel):
    runtime_write_count: int = Field(default=0, ge=0)
    legacy_fallback_count: int = Field(default=0, ge=0)
    parity_percent: float = Field(default=0, ge=0, le=100)
    critical_mismatch: int = Field(default=0, ge=0)
    duplicate_execution: int = Field(default=0, ge=0)
    rollback_count: int = Field(default=0, ge=0)
    canary_observation_days: int = Field(default=0, ge=0)
    canary_execution_count: int = Field(default=0, ge=0)
    execution_success_percent: float = Field(default=0, ge=0, le=100)
    promotion_status: RuntimePrimaryStatus
    validation_latency_ms: float = Field(default=0, ge=0)
    write_latency_ms: float = Field(default=0, ge=0)
    fallback_latency_ms: float = Field(default=0, ge=0)
    total_latency_ms: float = Field(default=0, ge=0)
    throughput_per_second: float | None = Field(default=None, ge=0)
    overhead_percent: float | None = Field(default=None, ge=0)


class RuntimePrimaryReport(_RuntimePrimaryModel):
    scope: PlanningRuntimeScope
    publication_id: str = Field(min_length=1, max_length=120)
    publication_version: int = Field(ge=1)
    mode: RuntimePrimaryMode
    status: RuntimePrimaryStatus
    decision: RuntimePrimaryDecision
    reason: str = Field(min_length=1, max_length=500)
    validation: RuntimePrimaryValidationResult
    metrics: RuntimePrimaryMetrics
    diagnostics: RuntimePrimaryDiagnostics
    duration_ms: float = Field(ge=0)
    outcome: RuntimePrimaryOutcome
    generated_at: datetime

    _validate_generated_at = field_validator("generated_at")(
        _timezone_aware
    )

    @model_validator(mode="after")
    def validate_outcome(self):
        if self.metrics.promotion_status is not self.status:
            raise ValueError("Metrics promotion status must match report.")
        if self.status is RuntimePrimaryStatus.PRIMARY:
            if (
                self.mode is not RuntimePrimaryMode.PRIMARY
                or self.decision is not RuntimePrimaryDecision.PROMOTED
                or self.outcome
                is not RuntimePrimaryOutcome.RUNTIME_WRITE_COMMITTED
                or self.metrics.runtime_write_count != 1
            ):
                raise ValueError("PRIMARY requires one committed Runtime write.")
        if self.status is RuntimePrimaryStatus.ROLLED_BACK:
            if (
                self.mode is not RuntimePrimaryMode.ROLLBACK
                or self.decision is not RuntimePrimaryDecision.FALLBACK
                or self.outcome
                is not RuntimePrimaryOutcome.LEGACY_FALLBACK_ACTIVATED
                or self.metrics.legacy_fallback_count != 1
                or self.metrics.rollback_count != 1
            ):
                raise ValueError("ROLLED_BACK requires one Legacy fallback.")
        if self.status in {
            RuntimePrimaryStatus.DISABLED,
            RuntimePrimaryStatus.CANARY,
            RuntimePrimaryStatus.READY_TO_PROMOTE,
            RuntimePrimaryStatus.READY_TO_ROLLBACK,
            RuntimePrimaryStatus.REJECTED,
        } and (
            self.metrics.runtime_write_count
            or self.metrics.legacy_fallback_count
        ):
            raise ValueError("Non-operational reports cannot expose writes.")
        return self
