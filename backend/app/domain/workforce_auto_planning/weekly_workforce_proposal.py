from datetime import date as CalendarDate, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.core_language import OperationalUnit


class WeeklyWorkforceProposalStatus(str, Enum):
    DRAFT = "DRAFT"
    GENERATED = "GENERATED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"


class WeeklyWorkforceProposal(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    proposal_id: str = Field(min_length=1)
    organization_id: str = Field(min_length=1)
    period_start: CalendarDate
    period_end: CalendarDate
    operational_unit: OperationalUnit
    version: int = Field(gt=0, strict=True)
    input_snapshot_id: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    policy_set_identifier: str = Field(min_length=1)
    policy_set_version: str = Field(min_length=1)
    status: WeeklyWorkforceProposalStatus
    created_at: datetime

    @model_validator(mode="after")
    def validate_proposal_identity(self) -> "WeeklyWorkforceProposal":
        if self.period_end < self.period_start:
            raise ValueError("period_end cannot precede period_start")
        if not self.operational_unit.external_identifier.strip():
            raise ValueError("operational_unit cannot be empty")
        return self
