from datetime import date as CalendarDate
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.core_language import OperationalUnit, TimeWindow


class ProposedShiftAssignmentOrigin(str, Enum):
    AUTOMATIC = "AUTOMATIC"
    MANUAL = "MANUAL"


class ProposedShiftAssignmentStatus(str, Enum):
    PROPOSED = "PROPOSED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class ProposedAssignmentReason(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ProposedShiftAssignment(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    assignment_id: str = Field(min_length=1)
    organization_id: str = Field(min_length=1)
    workforce_member_id: str = Field(min_length=1)
    date: CalendarDate
    operational_unit: OperationalUnit
    shift_identifier: str | None = Field(default=None, min_length=1)
    time_window: TimeWindow
    capability_or_workload: str = Field(min_length=1)
    origin: ProposedShiftAssignmentOrigin
    status: ProposedShiftAssignmentStatus
    deterministic_priority: int = Field(ge=0, strict=True)
    reasons: tuple[ProposedAssignmentReason, ...] = Field(min_length=1)
    locked: bool = Field(strict=True)

    @model_validator(mode="after")
    def validate_operational_unit(self) -> "ProposedShiftAssignment":
        if not self.operational_unit.external_identifier.strip():
            raise ValueError("operational_unit cannot be empty")
        return self
