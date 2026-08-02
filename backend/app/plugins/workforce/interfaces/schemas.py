from datetime import date

from pydantic import BaseModel, Field, field_validator

from app.plugins.workforce.domain.models import (
    WorkforceChange,
    WorkforceCoverage,
    WorkforceDayStatus,
    WorkforceMember,
)


class WorkforceStatusResponse(BaseModel):
    enabled: bool = True
    member_count: int = 0
    latest_import: dict[str, object] | None = None


class WorkforceMembersResponse(BaseModel):
    items: list[WorkforceMember]


class WorkforceCalendarResponse(BaseModel):
    items: list[WorkforceDayStatus]


class WorkforceCoverageResponse(BaseModel):
    items: list[WorkforceCoverage]


class WorkforceChangesResponse(BaseModel):
    items: list[WorkforceChange]


class WorkforceMemberUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    first_name: str | None = Field(default=None, max_length=80)
    last_name: str | None = Field(default=None, max_length=80)
    role: str | None = Field(default=None, max_length=120)
    station: str | None = Field(default=None, max_length=120)
    employment_type: str | None = Field(default=None, max_length=120)
    contract_start: str | None = None
    contract_end: str | None = None
    weekly_hours: float | None = Field(default=None, ge=0, le=168)
    capabilities: list[str] | None = None
    operational_notes: str | None = Field(default=None, max_length=1000)
    is_reserve: bool | None = None
    active: bool | None = None
    actor: str = Field(default="local_operator", min_length=1, max_length=120)

    @field_validator("contract_start", "contract_end")
    @classmethod
    def valid_date(cls, value: str | None) -> str | None:
        if value:
            date.fromisoformat(value)
        return value


class WorkforceDayStatusRequest(BaseModel):
    workforce_member_id: int = Field(gt=0)
    date: str
    status_code: str = Field(min_length=1, max_length=80)
    availability: bool | None = None
    shift_code: str | None = Field(default=None, max_length=80)
    start_time: str | None = Field(default=None, max_length=20)
    end_time: str | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=1000)
    source_reference: str = Field(default="manual", max_length=240)
    actor: str = Field(default="local_operator", min_length=1, max_length=120)

    @field_validator("date")
    @classmethod
    def valid_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value


class ConsecutivityPolicyRequest(BaseModel):
    warning_threshold: int = Field(default=5, ge=1, le=30)
    rest_required_threshold: int = Field(default=6, ge=2, le=31)
    rest_break_days: int = Field(default=1, ge=1, le=7)


class ConsecutivityOverrideRequest(BaseModel):
    workforce_member_id: int = Field(gt=0)
    operation_date: str
    valid_until: str
    target_callability: str = Field(pattern="^(callable|limited|not_callable)$")
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("operation_date", "valid_until")
    @classmethod
    def valid_override_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value
