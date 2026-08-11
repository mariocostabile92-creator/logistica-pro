from enum import StrEnum

from pydantic import BaseModel, Field


class DriverShiftDistributionStatus(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    DISTRIBUTED = "DISTRIBUTED"
    SUPERSEDED = "SUPERSEDED"


class DriverShiftDeliveryStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    SENT = "SENT"
    FAILED = "FAILED"


class DriverShiftAccessStatus(StrEnum):
    NOT_OPENED = "NOT_OPENED"
    OPENED = "OPENED"
    ACKNOWLEDGED = "ACKNOWLEDGED"


class DriverShiftDistributionError(ValueError):
    code = "DRIVER_SHIFT_DISTRIBUTION_INVALID"


class DriverShiftDistributionNotFoundError(DriverShiftDistributionError):
    code = "DRIVER_SHIFT_DISTRIBUTION_NOT_FOUND"


class DriverShiftPersonalAccessNotFoundError(DriverShiftDistributionError):
    code = "DRIVER_SHIFT_PERSONAL_ACCESS_NOT_FOUND"


class DriverShiftDistribution(BaseModel):
    id: int
    organization_id: str
    driver_shift_planning_id: int
    planning_version: int = Field(ge=1)
    period_start: str
    period_end: str
    status: DriverShiftDistributionStatus
    created_at: str
    created_by: str
    updated_at: str


class DriverShiftDistributionRecipient(BaseModel):
    id: int
    workforce_member_id: int
    display_name: str
    shift_days_count: int = Field(ge=0)
    delivery_status: DriverShiftDeliveryStatus
    access_status: DriverShiftAccessStatus
    access_revoked: bool = False
    first_opened_at: str | None = None
    last_opened_at: str | None = None
    acknowledged_at: str | None = None


class DriverShiftDistributionSummary(BaseModel):
    recipients_total: int = Field(ge=0)
    ready: int = Field(ge=0)
    pending: int = Field(ge=0)
    opened: int = Field(ge=0)
    acknowledged: int = Field(ge=0)
    not_opened: int = Field(ge=0)


class DriverShiftDistributionReadModel(BaseModel):
    distribution: DriverShiftDistribution
    summary: DriverShiftDistributionSummary
    recipients: list[DriverShiftDistributionRecipient] = Field(default_factory=list)


class DriverShiftRecipientAccessLink(BaseModel):
    recipient_id: int
    access_url: str
    expires_at: str


class PersonalDriverShift(BaseModel):
    operational_date: str
    status: str
    availability: bool
    shift: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    station: str | None = None
    notes: str | None = None


class PersonalDriverShiftView(BaseModel):
    driver_name: str
    period_start: str
    period_end: str
    access_status: DriverShiftAccessStatus
    first_opened_at: str | None = None
    acknowledged_at: str | None = None
    shifts: list[PersonalDriverShift] = Field(default_factory=list)
