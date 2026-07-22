from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.core_language import OperationalUnit
from app.domain.planning_confirmation import (
    PlanningConfirmation,
    PlanningConfirmationState,
)


class _PublicationModel(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)


def _require_timezone(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("A timezone-aware datetime is required.")
    return value


class PlanningPublicationState(str, Enum):
    NOT_PUBLISHED = "NOT_PUBLISHED"
    READY_TO_PUBLISH = "READY_TO_PUBLISH"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    ERROR = "ERROR"


class PlanningPublicationScope(_PublicationModel):
    organization_id: str = Field(min_length=1, max_length=120)
    operational_unit: OperationalUnit
    planning_date: date


class PlanningPublicationPolicy(_PublicationModel):
    required_confirmation_state: PlanningConfirmationState = (
        PlanningConfirmationState.CONFIRMED
    )
    require_valid_confirmation: bool = True
    require_unique_active_publication: bool = True
    require_runtime_compatibility: bool = True
    require_fingerprint_match: bool = True
    require_version_match: bool = True
    require_valid_operational_unit: bool = True


class PlanningPublicationRuleResult(_PublicationModel):
    code: str = Field(min_length=1, max_length=120)
    passed: bool
    reason: str = Field(min_length=1, max_length=500)
    remediation_hint: str = Field(min_length=1, max_length=500)


class PlanningPublicationResult(_PublicationModel):
    state: PlanningPublicationState
    can_publish: bool
    rules: tuple[PlanningPublicationRuleResult, ...] = Field(
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
        if self.state is PlanningPublicationState.READY_TO_PUBLISH:
            if not self.can_publish or not all_passed:
                raise ValueError(
                    "READY_TO_PUBLISH requires every rule to pass."
                )
        elif self.can_publish:
            raise ValueError("Only READY_TO_PUBLISH can be publishable.")
        if self.state is PlanningPublicationState.PUBLISHED and not all_passed:
            raise ValueError("A published result requires every rule to pass.")
        if self.state in {
            PlanningPublicationState.NOT_PUBLISHED,
            PlanningPublicationState.FAILED,
        } and all_passed:
            raise ValueError("A non-publishable result requires a failed rule.")
        return self


class PlanningPublicationValidationContext(_PublicationModel):
    scope: PlanningPublicationScope
    requested_confirmation_id: str | None = Field(default=None, max_length=120)
    requested_confirmation_version: int | None = Field(default=None, ge=1)
    requested_confirmation_fingerprint: str | None = Field(
        default=None,
        max_length=64,
    )
    confirmation: PlanningConfirmation | None = None
    runtime_compatible: bool
    operational_unit_valid: bool
    active_publication: "PlanningPublication | None" = None
    evaluated_at: datetime

    _validate_evaluated_at = field_validator("evaluated_at")(
        _require_timezone
    )


class PlanningPublication(_PublicationModel):
    publication_id: str = Field(min_length=1, max_length=120)
    scope: PlanningPublicationScope
    state: PlanningPublicationState = PlanningPublicationState.PUBLISHED
    version: int = Field(ge=1)
    confirmation_id: str = Field(min_length=1, max_length=120)
    confirmation_version: int = Field(ge=1)
    confirmation_fingerprint: str = Field(min_length=64, max_length=64)
    fingerprint: str = Field(min_length=64, max_length=64)
    actor: str = Field(min_length=1, max_length=120)
    published_at: datetime
    validation: PlanningPublicationResult

    _validate_published_at = field_validator("published_at")(
        _require_timezone
    )

    @model_validator(mode="after")
    def validate_publication(self):
        if self.state is not PlanningPublicationState.PUBLISHED:
            raise ValueError("A persisted publication must be PUBLISHED.")
        if self.validation.state is not PlanningPublicationState.READY_TO_PUBLISH:
            raise ValueError("A publication requires a successful validation.")
        return self


class PlanningPublicationHistory(_PublicationModel):
    scope: PlanningPublicationScope
    total: int = Field(ge=0)
    publications: tuple[PlanningPublication, ...] = Field(
        default_factory=tuple,
        max_length=100,
    )

    @model_validator(mode="after")
    def validate_history(self):
        if self.total < len(self.publications):
            raise ValueError("History total cannot be smaller than the page.")
        if any(
            item.scope.organization_id != self.scope.organization_id
            or (
                item.scope.operational_unit.external_identifier
                != self.scope.operational_unit.external_identifier
            )
            or item.scope.planning_date != self.scope.planning_date
            for item in self.publications
        ):
            raise ValueError("Every publication must share the history scope.")
        timestamps = tuple(item.published_at for item in self.publications)
        if timestamps != tuple(sorted(timestamps, reverse=True)):
            raise ValueError("Publications must be newest first.")
        return self


class PlanningPublicationReport(_PublicationModel):
    state: PlanningPublicationState
    result: PlanningPublicationResult
    current: PlanningPublication | None = None
    history: PlanningPublicationHistory
    generated_at: datetime

    _validate_generated_at = field_validator("generated_at")(
        _require_timezone
    )

    @model_validator(mode="after")
    def validate_report(self):
        if self.state is not self.result.state:
            raise ValueError("Report and result states must match.")
        if self.state is PlanningPublicationState.PUBLISHED and self.current is None:
            raise ValueError("A published report requires a current plan.")
        return self


PlanningPublicationValidationContext.model_rebuild()
