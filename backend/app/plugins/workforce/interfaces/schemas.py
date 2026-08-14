from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.plugins.workforce.domain.models import (
    OperationalCycle,
    WorkforceChange,
    WorkforceCoverage,
    WorkforceDayStatus,
    WorkforceMember,
)
from app.plugins.workforce.domain.day_member_batch import DayMemberOverwritePolicy


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


class ManualCoverageRequirementRequest(BaseModel):
    cycle: Literal["NEXT_DAY", "SAME_DAY"]
    segment: Literal["A", "B_C"] | None = None
    forecast_routes: int = Field(ge=0)

    @model_validator(mode="after")
    def valid_bucket(self):
        valid = (
            (self.cycle == "NEXT_DAY" and self.segment is None)
            or (self.cycle == "SAME_DAY" and self.segment in {"A", "B_C"})
        )
        if not valid:
            raise ValueError("Combinazione ciclo/segmento non supportata.")
        return self


class ManualCoverageUpdateRequest(BaseModel):
    expected_fingerprint: str = Field(
        min_length=64, max_length=64, pattern="^[0-9a-f]{64}$"
    )
    requirements: list[ManualCoverageRequirementRequest] = Field(
        min_length=1, max_length=3
    )

    @field_validator("requirements")
    @classmethod
    def unique_buckets(
        cls, values: list[ManualCoverageRequirementRequest]
    ) -> list[ManualCoverageRequirementRequest]:
        keys = [(item.cycle, item.segment) for item in values]
        if len(keys) != len(set(keys)):
            raise ValueError("Un bucket non puo essere ripetuto.")
        return values


class WorkforceChangesResponse(BaseModel):
    items: list[WorkforceChange]


class WorkforceMemberUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    first_name: str | None = Field(default=None, max_length=80)
    last_name: str | None = Field(default=None, max_length=80)
    role: str | None = Field(default=None, max_length=120)
    station: str | None = Field(default=None, max_length=120)
    employment_type: str | None = Field(default=None, max_length=120)
    operational_cycle: OperationalCycle | None = None
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
    operational_activity: str | None = Field(default=None, max_length=160)
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


class WorkforceMemberCreateRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    external_identifier: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = Field(default="driver", max_length=120)
    station: str | None = Field(default=None, max_length=120)
    employment_type: str | None = Field(default=None, max_length=120)
    operational_cycle: OperationalCycle = OperationalCycle.NOT_SET
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=254)
    operational_notes: str | None = Field(default=None, max_length=1000)
    active: bool = True
    actor: str = Field(default="local_operator", min_length=1, max_length=120)

    @field_validator("first_name", "last_name")
    @classmethod
    def normalized_required_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Nome e cognome sono obbligatori.")
        return normalized


class WorkforceDayStatusBatchRequest(BaseModel):
    operational_activity: str | None = Field(default=None, max_length=160)
    workforce_member_id: int = Field(gt=0)
    dates: list[str] = Field(min_length=1, max_length=31)
    status_code: str = Field(min_length=1, max_length=80)
    availability: bool | None = None
    shift_code: str | None = Field(default=None, max_length=80)
    start_time: str | None = Field(default=None, max_length=20)
    end_time: str | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=1000)
    source_reference: str = Field(default="manual_bulk", max_length=240)
    actor: str = Field(default="local_operator", min_length=1, max_length=120)

    @field_validator("dates")
    @classmethod
    def valid_dates(cls, values: list[str]) -> list[str]:
        normalized = [date.fromisoformat(value).isoformat() for value in values]
        if len(set(normalized)) != len(normalized):
            raise ValueError("Le date selezionate non possono essere duplicate.")
        return normalized


class WorkforceDayStatusBatchResponse(BaseModel):
    items: list[WorkforceDayStatus]


class WorkforceDayMemberBatchRequest(BaseModel):
    operational_date: str
    workforce_member_ids: list[int] = Field(min_length=1, max_length=200)
    status_code: str = Field(min_length=1, max_length=80)
    availability: bool | None = None
    shift_code: str | None = Field(default=None, max_length=80)
    operational_activity: str | None = Field(default=None, max_length=160)
    start_time: str | None = Field(default=None, max_length=20)
    end_time: str | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=1000)
    source_reference: str = Field(default="manual_day_planning", max_length=240)
    overwrite_policy: DayMemberOverwritePolicy = DayMemberOverwritePolicy.APPLY_TO_EMPTY_ONLY
    confirm_overwrite: bool = False
    confirm_unavailable_override: bool = False
    actor: str = Field(default="local_operator", min_length=1, max_length=120)

    @field_validator("operational_date")
    @classmethod
    def valid_operational_date(cls, value: str) -> str:
        return date.fromisoformat(value).isoformat()

    @field_validator("workforce_member_ids")
    @classmethod
    def valid_member_ids(cls, values: list[int]) -> list[int]:
        if any(value <= 0 for value in values):
            raise ValueError("Gli ID driver devono essere positivi.")
        if len(values) != len(set(values)):
            raise ValueError("Un driver non puo essere selezionato due volte.")
        return values


class WorkforceWeekCopyRequest(BaseModel):
    workforce_member_id: int = Field(gt=0)
    target_week_start: str
    expected_fingerprint: str = Field(min_length=64, max_length=64)
    actor: str = Field(default="local_operator", min_length=1, max_length=120)

    @field_validator("target_week_start")
    @classmethod
    def valid_target_week_start(cls, value: str) -> str:
        return date.fromisoformat(value).isoformat()


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


class DriverShiftDistributionPrepareRequest(BaseModel):
    period_start: str
    period_end: str

    @field_validator("period_start", "period_end")
    @classmethod
    def valid_distribution_date(cls, value: str) -> str:
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


class LegacyCanonicalPublishRequest(BaseModel):
    expected_version: int = Field(gt=0)
    expected_fingerprint: str = Field(min_length=64, max_length=64)


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


class DriverShiftPortalTokenRequest(BaseModel):
    token: str = Field(min_length=1, max_length=256)


class DriverShiftPortalLoginRequest(BaseModel):
    portal_token: str = Field(min_length=1, max_length=256)
    access_code: str = Field(min_length=1, max_length=64)
    pin: str = Field(min_length=1, max_length=32)
    remember_device: bool = False
