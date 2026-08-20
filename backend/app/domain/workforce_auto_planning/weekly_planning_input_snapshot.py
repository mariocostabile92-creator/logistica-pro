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


class AssignedTimeStatus(str, Enum):
    KNOWN = "KNOWN"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class AssignedTimeSnapshot(_ImmutableSnapshotModel):
    status: AssignedTimeStatus = AssignedTimeStatus.KNOWN
    value: Decimal | None = Field(default=None, ge=0)
    unit: AssignedTimeUnit | None = None

    @model_validator(mode="after")
    def validate_status_payload(self) -> "AssignedTimeSnapshot":
        if self.status == AssignedTimeStatus.UNKNOWN:
            if self.value is not None or self.unit is not None:
                raise ValueError(
                    "UNKNOWN assigned time cannot include value or unit"
                )
            return self

        if self.value is None or self.unit is None:
            raise ValueError(
                f"{self.status.value} assigned time requires value and unit"
            )
        return self


class ContractStateSourceKind(str, Enum):
    CURRENT_MEMBER_CONTRACT_STATE = "CURRENT_MEMBER_CONTRACT_STATE"


class CurrentMemberContractStateSnapshot(_ImmutableSnapshotModel):
    source_kind: ContractStateSourceKind = (
        ContractStateSourceKind.CURRENT_MEMBER_CONTRACT_STATE
    )
    employment_type: str | None = Field(default=None, min_length=1)
    contract_start: CalendarDate | None = None
    contract_end: CalendarDate | None = None
    weekly_hours: Decimal | None = Field(default=None, ge=0)
    is_reserve: bool | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def validate_contract_period(self) -> "CurrentMemberContractStateSnapshot":
        if (
            self.contract_start is not None
            and self.contract_end is not None
            and self.contract_end < self.contract_start
        ):
            raise ValueError("contract_end cannot precede contract_start")
        return self


class CandidateOperationalUnitScopeStatus(str, Enum):
    MATCHED = "MATCHED"
    MISMATCHED = "MISMATCHED"
    UNKNOWN = "UNKNOWN"


class CandidateOperationalUnitScope(_ImmutableSnapshotModel):
    status: CandidateOperationalUnitScopeStatus
    requested_unit: OperationalUnit
    candidate_unit: OperationalUnit | None = None

    @model_validator(mode="after")
    def validate_unit_presence(self) -> "CandidateOperationalUnitScope":
        if not self.requested_unit.external_identifier.strip():
            raise ValueError("requested_unit cannot be empty")

        if self.status == CandidateOperationalUnitScopeStatus.UNKNOWN:
            if self.candidate_unit is not None:
                raise ValueError("UNKNOWN scope cannot include candidate_unit")
            return self

        if self.candidate_unit is None:
            raise ValueError(f"{self.status.value} scope requires candidate_unit")
        if not self.candidate_unit.external_identifier.strip():
            raise ValueError("candidate_unit cannot be empty")
        return self


class WorkforceCandidateAvailabilitySnapshot(_ImmutableSnapshotModel):
    date: CalendarDate
    time_window: TimeWindow | None = None
    availability: ResourceAvailability


class ApprovedAssignmentSnapshot(_ImmutableSnapshotModel):
    assignment_reference: str = Field(min_length=1)
    date: CalendarDate
    operational_unit: OperationalUnit | None = None
    shift_identifier: str | None = Field(default=None, min_length=1)
    time_window: TimeWindow
    assigned_time: AssignedTimeSnapshot


class WorkforceCandidateSnapshot(_ImmutableSnapshotModel):
    organization_id: str = Field(min_length=1)
    human_resource: HumanResource
    availability: tuple[WorkforceCandidateAvailabilitySnapshot, ...] = Field(
        default_factory=tuple
    )
    applicable_contract_state: CurrentMemberContractStateSnapshot
    operational_unit_scope: CandidateOperationalUnitScope
    recent_consecutivity: int | None = Field(ge=0, strict=True)
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
            if (
                demand.operational_unit.external_identifier
                != self.operational_unit.external_identifier
            ):
                raise ValueError(
                    "all demands must belong to the snapshot operational unit"
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
