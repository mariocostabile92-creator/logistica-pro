from datetime import date as CalendarDate, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.core_language import (
    HumanResource,
    OperationalUnit,
    ResourceAvailability,
    ResourceKind,
    TimeWindow,
)
from app.domain.workforce_auto_planning.constraint_evaluation import (
    ConstraintEvidence,
)
from app.domain.workforce_auto_planning.operational_demand import (
    OperationalDemand,
)


class _ImmutableSnapshotModel(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)


class AssignedTimeUnit(str, Enum):
    MINUTES = "MINUTES"
    HOURS = "HOURS"


class AssignedTimeSnapshot(_ImmutableSnapshotModel):
    value: Decimal = Field(ge=0)
    unit: AssignedTimeUnit


class WorkforceCandidateAvailabilitySnapshot(_ImmutableSnapshotModel):
    date: CalendarDate
    time_window: TimeWindow | None = None
    availability: ResourceAvailability


class ApprovedAssignmentSnapshot(_ImmutableSnapshotModel):
    assignment_reference: str = Field(min_length=1)
    date: CalendarDate
    operational_unit: OperationalUnit
    shift_identifier: str = Field(min_length=1)
    time_window: TimeWindow
    assigned_time: AssignedTimeSnapshot


class WorkforceCandidateSnapshot(_ImmutableSnapshotModel):
    organization_id: str = Field(min_length=1)
    human_resource: HumanResource
    availability: tuple[WorkforceCandidateAvailabilitySnapshot, ...] = Field(
        default_factory=tuple
    )
    applicable_contract_reference: str = Field(min_length=1)
    recent_consecutivity: int = Field(ge=0, strict=True)
    already_approved_assignments: tuple[ApprovedAssignmentSnapshot, ...] = Field(
        default_factory=tuple
    )
    already_assigned_minutes_or_hours: AssignedTimeSnapshot
    evidence: tuple[ConstraintEvidence, ...] = Field(default_factory=tuple)

    @property
    def workforce_member_id(self) -> str:
        return self.human_resource.external_identifier

    @property
    def capabilities(self) -> tuple[str, ...]:
        return self.human_resource.capabilities

    @model_validator(mode="after")
    def validate_resource_identity(self) -> "WorkforceCandidateSnapshot":
        resource_identifier = self.human_resource.external_identifier
        if not resource_identifier.strip():
            raise ValueError("workforce_member_id cannot be empty")
        for item in self.availability:
            availability = item.availability
            if availability.resource_kind != ResourceKind.HUMAN_RESOURCE:
                raise ValueError("availability must describe a human resource")
            if availability.resource_identifier != resource_identifier:
                raise ValueError(
                    "availability must belong to the snapshot human resource"
                )
        return self


class WeeklyPlanningInputSnapshot(_ImmutableSnapshotModel):
    snapshot_id: str = Field(min_length=1)
    organization_id: str = Field(min_length=1)
    period_start: CalendarDate
    period_end: CalendarDate
    operational_unit: OperationalUnit
    demands: tuple[OperationalDemand, ...] = Field(default_factory=tuple)
    workforce_candidates: tuple[WorkforceCandidateSnapshot, ...] = Field(
        default_factory=tuple
    )
    policy_set_identifier: str = Field(min_length=1)
    policy_set_version: str = Field(min_length=1)
    created_at: datetime
    fingerprint: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_snapshot_scope(self) -> "WeeklyPlanningInputSnapshot":
        if self.period_end < self.period_start:
            raise ValueError("period_end cannot precede period_start")
        if not self.operational_unit.external_identifier.strip():
            raise ValueError("operational_unit cannot be empty")

        for demand in self.demands:
            if demand.organization_id != self.organization_id:
                raise ValueError(
                    "all demands must belong to the snapshot organization"
                )
            if not self.period_start <= demand.date <= self.period_end:
                raise ValueError("all demands must fall within the snapshot period")

        for candidate in self.workforce_candidates:
            if candidate.organization_id != self.organization_id:
                raise ValueError(
                    "all workforce candidates must belong to the snapshot "
                    "organization"
                )
        return self
