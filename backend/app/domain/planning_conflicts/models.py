from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.core_language import OperationalUnit
from app.domain.planning_readiness import PlanningReadinessResult
from app.domain.planning_readiness import (
    PlanningReadinessScore,
    PlanningReadinessStatus,
)


class _ConflictModel(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)


def _require_timezone(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("A timezone-aware datetime is required.")
    return value


class PlanningConflictCategory(str, Enum):
    WORKFORCE = "WORKFORCE"
    FLEET = "FLEET"
    CAPABILITY = "CAPABILITY"
    OPERATIONAL_UNIT = "OPERATIONAL_UNIT"
    VALIDATION = "VALIDATION"
    FRESHNESS = "FRESHNESS"
    VERSION = "VERSION"
    DEPENDENCY = "DEPENDENCY"
    RUNTIME = "RUNTIME"
    LEGACY = "LEGACY"


class PlanningConflictSeverity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PlanningConflictDiagnostic(_ConflictModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    source: str = Field(min_length=1)
    details: tuple[str, ...] = Field(default_factory=tuple)


class PlanningConflictSuggestion(_ConflictModel):
    action: str = Field(min_length=1)
    workspace: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class PlanningConflict(_ConflictModel):
    id: str = Field(min_length=1)
    code: str = Field(min_length=1)
    category: PlanningConflictCategory
    severity: PlanningConflictSeverity
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    operational_unit: OperationalUnit
    planning_date: date
    source: str = Field(min_length=1)
    blocking: bool
    affected_entities: tuple[str, ...] = Field(default_factory=tuple)
    diagnostics: tuple[PlanningConflictDiagnostic, ...] = Field(min_length=1)
    suggestion: PlanningConflictSuggestion
    documentation_reference: str = Field(min_length=1)
    timestamp: datetime

    _validate_timestamp = field_validator("timestamp")(_require_timezone)


class PlanningConflictGroup(_ConflictModel):
    category: PlanningConflictCategory
    label: str = Field(min_length=1)
    total_conflicts: int = Field(ge=1)
    total_blocking: int = Field(ge=0)
    highest_severity: PlanningConflictSeverity
    conflict_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_totals(self):
        if self.total_conflicts != len(self.conflict_ids):
            raise ValueError("Group total must match conflict identifiers.")
        if self.total_blocking > self.total_conflicts:
            raise ValueError("Blocking conflicts cannot exceed group total.")
        return self


class PlanningConflictReport(_ConflictModel):
    total_conflicts: int = Field(ge=0)
    total_blocking: int = Field(ge=0)
    total_warnings: int = Field(ge=0)
    groups: tuple[PlanningConflictGroup, ...] = Field(default_factory=tuple)
    conflicts: tuple[PlanningConflict, ...] = Field(default_factory=tuple)
    timestamp: datetime
    planning_version: str | None = None
    planning_date: date
    operational_unit: OperationalUnit

    _validate_timestamp = field_validator("timestamp")(_require_timezone)

    @model_validator(mode="after")
    def validate_totals(self):
        if self.total_conflicts != len(self.conflicts):
            raise ValueError("Report total must match conflicts.")
        blocking = sum(item.blocking for item in self.conflicts)
        if self.total_blocking != blocking:
            raise ValueError("Blocking total must reflect conflicts.")
        if self.total_warnings != self.total_conflicts - blocking:
            raise ValueError("Warning total must reflect non-blocking conflicts.")
        grouped_ids = tuple(
            conflict_id
            for group in self.groups
            for conflict_id in group.conflict_ids
        )
        if set(grouped_ids) != {item.id for item in self.conflicts}:
            raise ValueError("Every conflict must belong to one group.")
        return self


class PlanningConflictReadiness(_ConflictModel):
    status: PlanningReadinessStatus
    score: PlanningReadinessScore
    is_ready: bool
    rationale: str = Field(min_length=1)
    evaluated_at: datetime
    operational_unit: OperationalUnit
    planning_date: date
    envelope_version: str | None = None
    legacy_flow_active: bool = True

    _validate_evaluated_at = field_validator("evaluated_at")(
        _require_timezone
    )

    @classmethod
    def from_readiness(
        cls,
        readiness: PlanningReadinessResult,
    ) -> "PlanningConflictReadiness":
        return cls(
            status=readiness.status,
            score=readiness.score,
            is_ready=readiness.is_ready,
            rationale=readiness.rationale,
            evaluated_at=readiness.evaluated_at,
            operational_unit=readiness.operational_unit,
            planning_date=readiness.planning_date,
            envelope_version=readiness.envelope_version,
            legacy_flow_active=readiness.legacy_flow_active,
        )


class PlanningConflictResult(_ConflictModel):
    readiness: PlanningConflictReadiness
    report: PlanningConflictReport

    @model_validator(mode="after")
    def validate_context(self):
        if self.readiness.planning_date != self.report.planning_date:
            raise ValueError("Readiness and conflict report dates must match.")
        readiness_unit = self.readiness.operational_unit.external_identifier
        report_unit = self.report.operational_unit.external_identifier
        if readiness_unit != report_unit:
            raise ValueError("Readiness and conflict report units must match.")
        return self
