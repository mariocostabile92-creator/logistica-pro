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
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=254)
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


class DriverShiftPlanningCreateRequest(BaseModel):
    period_start: str
    period_end: str
    label: str | None = Field(default=None, max_length=160)

    @field_validator("period_start", "period_end")
    @classmethod
    def valid_planning_date(cls, value: str) -> str:
        return date.fromisoformat(value).isoformat()


class DriverShiftPlanningSourceRequest(BaseModel):
    workforce_import_id: int = Field(gt=0)
    source_order: int | None = Field(default=None, ge=0)


class DriverShiftPlanningImportReference(BaseModel):
    workforce_import_id: int = Field(gt=0)
    fingerprint: str
    original_filename: str
    imported_at: str


class DriverShiftPlanningReplaceSourcesRequest(BaseModel):
    workforce_import_ids: list[int] = Field(min_length=1, max_length=100)

    @field_validator("workforce_import_ids")
    @classmethod
    def valid_import_ids(cls, value: list[int]) -> list[int]:
        if any(item <= 0 for item in value):
            raise ValueError("Gli ID import devono essere positivi.")
        if len(set(value)) != len(value):
            raise ValueError("Una source non può essere ripetuta.")
        return value


class DriverShiftPlanningResolutionRequest(BaseModel):
    expected_version: int = Field(gt=0)
    resolution_type: str = Field(pattern="^(USE_SOURCE_ROW|EXCLUDE)$")
    selected_source_row_id: int | None = Field(default=None, gt=0)
    workforce_member_id: int | None = Field(default=None, gt=0)


class DriverShiftPlanningPublishRequest(BaseModel):
    expected_version: int = Field(gt=0)
    expected_preview_fingerprint: str = Field(min_length=64, max_length=64)


class DriverShiftBatchPrepareRequest(BaseModel):
    recipient_ids: list[int] | None = Field(default=None, max_length=500)

    @field_validator("recipient_ids")
    @classmethod
    def valid_recipient_ids(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        if any(item <= 0 for item in value):
            raise ValueError("Gli ID destinatario devono essere positivi.")
        if len(value) != len(set(value)):
            raise ValueError("Un destinatario non può essere ripetuto.")
        return value
