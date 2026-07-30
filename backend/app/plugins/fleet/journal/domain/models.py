from enum import Enum

from pydantic import BaseModel, Field


class OperationType(str, Enum):
    CHECK_OUT = "check_out"
    CHECK_IN = "check_in"


class SessionStatus(str, Enum):
    OPEN = "open"
    COMPLETED = "completed"


class SessionLifecycleStatus(str, Enum):
    GENERATED = "generated"
    OPENED = "opened"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class JournalSession(BaseModel):
    id: str
    token_hash: str = Field(exclude=True)
    operation_type: OperationType
    asset_id: int
    plate_snapshot: str
    declared_driver_identifier: str
    operational_shift: str | None
    status: SessionStatus
    created_at: str
    expires_at: str
    completed_at: str | None = None
    source: str = "driver"
    lifecycle_status: SessionLifecycleStatus = SessionLifecycleStatus.IN_PROGRESS
    scheduled_at: str | None = None
    opened_at: str | None = None
    in_progress_at: str | None = None


class AssetMovement(BaseModel):
    id: str
    schema_version: str = "1.0"
    organization_id: str
    operational_unit_id: str
    asset_id: int
    plate_snapshot: str
    declared_driver_identifier: str
    operation_type: OperationType
    operational_shift: str | None = None
    occurred_at: str
    timezone: str
    odometer_km: int
    fuel_percentage: int
    cleanliness_status: str | None = None
    anomaly_present: bool
    anomaly_description: str | None = None
    operational_note: str | None = None
    client_submission_id: str
    created_at: str


class MovementEquipment(BaseModel):
    movement_id: str
    equipment_code: str
    equipment_label_snapshot: str
    equipment_status: str
    note: str | None = None


class MovementMedia(BaseModel):
    id: str
    movement_id: str | None = None
    media_type: str
    phase: str
    storage_key: str
    verified_mime_type: str
    size_bytes: int
    sha256: str
    display_order: int
