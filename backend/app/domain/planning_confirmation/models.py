from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.core_language import OperationalUnit
from app.domain.planning_conflicts import PlanningConflictResult
from app.domain.planning_drafts import PlanningDraft
from app.domain.planning_inputs import PlanningInputEnvelope
from app.domain.planning_readiness import (
    PlanningReadinessResult,
    PlanningReadinessStatus,
)


class _ConfirmationModel(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)


def _require_timezone(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("A timezone-aware datetime is required.")
    return value


class PlanningConfirmationState(str, Enum):
    NOT_READY = "NOT_READY"
    READY_TO_CONFIRM = "READY_TO_CONFIRM"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    ERROR = "ERROR"


class PlanningConfirmationScope(_ConfirmationModel):
    organization_id: str = Field(min_length=1, max_length=120)
    operational_unit: OperationalUnit
    planning_date: date


class PlanningConfirmationPolicy(_ConfirmationModel):
    required_readiness_status: PlanningReadinessStatus = (
        PlanningReadinessStatus.READY
    )
    required_runtime_status: str = "ready"
    require_saved_draft: bool = True
    require_no_blocking_conflicts: bool = True
    require_valid_envelope: bool = True
    require_unique_active_confirmation: bool = True


class PlanningConfirmationRuleResult(_ConfirmationModel):
    code: str = Field(min_length=1, max_length=120)
    passed: bool
    reason: str = Field(min_length=1, max_length=500)
    remediation_hint: str = Field(min_length=1, max_length=500)


class PlanningConfirmationResult(_ConfirmationModel):
    state: PlanningConfirmationState
    can_confirm: bool
    rules: tuple[PlanningConfirmationRuleResult, ...] = Field(
        min_length=1,
        max_length=20,
    )
    rationale: str = Field(min_length=1, max_length=500)
    evaluated_at: datetime

    _validate_evaluated_at = field_validator("evaluated_at")(
        _require_timezone
    )

    @model_validator(mode="after")
    def validate_result(self):
        all_passed = all(rule.passed for rule in self.rules)
        if self.state is PlanningConfirmationState.READY_TO_CONFIRM:
            if not self.can_confirm or not all_passed:
                raise ValueError("READY_TO_CONFIRM requires every rule to pass.")
        elif self.can_confirm:
            raise ValueError("Only READY_TO_CONFIRM can be confirmable.")
        if self.state is PlanningConfirmationState.CONFIRMED and not all_passed:
            raise ValueError("A confirmed result requires every rule to pass.")
        if self.state in {
            PlanningConfirmationState.NOT_READY,
            PlanningConfirmationState.REJECTED,
        } and all_passed:
            raise ValueError("A non-confirmable result requires a failed rule.")
        return self


class PlanningConfirmationValidationContext(_ConfirmationModel):
    scope: PlanningConfirmationScope
    requested_draft_id: str | None = Field(default=None, max_length=120)
    requested_draft_version: int | None = Field(default=None, ge=1)
    draft: PlanningDraft | None = None
    readiness: PlanningReadinessResult
    conflicts: PlanningConflictResult
    envelope: PlanningInputEnvelope | None = None
    runtime_status: str = Field(min_length=1, max_length=40)
    runtime_compatible: bool
    active_confirmation: "PlanningConfirmation | None" = None
    evaluated_at: datetime

    _validate_evaluated_at = field_validator("evaluated_at")(
        _require_timezone
    )


class PlanningConfirmation(_ConfirmationModel):
    confirmation_id: str = Field(min_length=1, max_length=120)
    scope: PlanningConfirmationScope
    state: PlanningConfirmationState = PlanningConfirmationState.CONFIRMED
    version: int = Field(ge=1)
    draft_id: str = Field(min_length=1, max_length=120)
    draft_version: int = Field(ge=1)
    draft_name: str = Field(min_length=1, max_length=120)
    draft_note: str | None = Field(default=None, max_length=1000)
    readiness_status: PlanningReadinessStatus
    readiness_score: int = Field(ge=0, le=100)
    envelope_version: str = Field(min_length=1, max_length=200)
    envelope_fingerprint: str = Field(min_length=1, max_length=200)
    fingerprint: str = Field(min_length=64, max_length=64)
    actor: str = Field(min_length=1, max_length=120)
    confirmed_at: datetime
    validation: PlanningConfirmationResult

    _validate_confirmed_at = field_validator("confirmed_at")(
        _require_timezone
    )

    @model_validator(mode="after")
    def validate_confirmation(self):
        if self.state is not PlanningConfirmationState.CONFIRMED:
            raise ValueError("A persisted confirmation must be CONFIRMED.")
        if self.validation.state is not PlanningConfirmationState.READY_TO_CONFIRM:
            raise ValueError("A confirmation requires a successful validation.")
        if self.readiness_status is not PlanningReadinessStatus.READY:
            raise ValueError("A confirmation requires READY readiness.")
        return self


class PlanningConfirmationHistory(_ConfirmationModel):
    scope: PlanningConfirmationScope
    total: int = Field(ge=0)
    confirmations: tuple[PlanningConfirmation, ...] = Field(
        default_factory=tuple,
        max_length=100,
    )

    @model_validator(mode="after")
    def validate_history(self):
        if self.total < len(self.confirmations):
            raise ValueError("History total cannot be smaller than the page.")
        if any(item.scope != self.scope for item in self.confirmations):
            raise ValueError("Every confirmation must share the history scope.")
        times = tuple(item.confirmed_at for item in self.confirmations)
        if times != tuple(sorted(times, reverse=True)):
            raise ValueError("Confirmations must be newest first.")
        return self


class PlanningConfirmationReport(_ConfirmationModel):
    state: PlanningConfirmationState
    result: PlanningConfirmationResult
    current: PlanningConfirmation | None = None
    history: PlanningConfirmationHistory
    generated_at: datetime

    _validate_generated_at = field_validator("generated_at")(
        _require_timezone
    )

    @model_validator(mode="after")
    def validate_report(self):
        if self.state is not self.result.state:
            raise ValueError("Report and result states must match.")
        if self.state is PlanningConfirmationState.CONFIRMED:
            if self.current is None:
                raise ValueError("A confirmed report requires a current plan.")
        return self


PlanningConfirmationValidationContext.model_rebuild()
