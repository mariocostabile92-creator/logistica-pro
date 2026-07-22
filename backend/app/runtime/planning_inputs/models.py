from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.planning_inputs import (
    PlanningInputEnvelope,
    PlanningInputSnapshot,
)


class _RuntimeModel(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)


def _require_timezone(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("A timezone-aware datetime is required.")
    return value


class PlanningInputRuntimeStatus(str, Enum):
    READY = "ready"
    STALE = "stale"
    PARTIAL = "partial"
    MISSING = "missing"
    INVALID = "invalid"
    INCOMPATIBLE = "incompatible"


class PlanningInputCompatibilityCheck(_RuntimeModel):
    code: str = Field(min_length=1)
    compatible: bool | None
    message: str = Field(min_length=1)


class PlanningInputCompatibility(_RuntimeModel):
    compatible: bool
    checks: tuple[PlanningInputCompatibilityCheck, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_result(self):
        expected = all(check.compatible is True for check in self.checks)
        if self.compatible != expected:
            raise ValueError("Compatibility must reflect every explicit check.")
        return self


class PlanningInputDiagnostics(_RuntimeModel):
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    errors: tuple[str, ...] = Field(default_factory=tuple)
    reasons: tuple[str, ...] = Field(default_factory=tuple)


class PlanningInputCompositionReport(_RuntimeModel):
    workforce: PlanningInputSnapshot | None
    fleet: PlanningInputSnapshot | None
    status: PlanningInputRuntimeStatus
    compatibility: PlanningInputCompatibility
    diagnostics: PlanningInputDiagnostics
    timestamp: datetime
    legacy_flow_active: bool = True

    _validate_timestamp = field_validator("timestamp")(_require_timezone)


class PlanningInputCompositionResult(_RuntimeModel):
    status: PlanningInputRuntimeStatus
    envelope: PlanningInputEnvelope | None = None
    report: PlanningInputCompositionReport

    @model_validator(mode="after")
    def validate_result(self):
        if self.status != self.report.status:
            raise ValueError("Result and report statuses must match.")
        if self.status is PlanningInputRuntimeStatus.READY:
            if self.envelope is None:
                raise ValueError("A READY result requires an envelope.")
        elif self.envelope is not None:
            raise ValueError("Only a READY result can expose an envelope.")
        return self

    @property
    def diagnostics(self) -> PlanningInputDiagnostics:
        return self.report.diagnostics

    @property
    def compatibility(self) -> PlanningInputCompatibility:
        return self.report.compatibility

    @property
    def legacy_flow_active(self) -> bool:
        return self.report.legacy_flow_active
