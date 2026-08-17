from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SessionCreateRequest(BaseModel):
    operation_type: Literal["check_out", "check_in"]
    plate: str = Field(min_length=1, max_length=40)
    declared_driver_identifier: str = Field(min_length=1, max_length=120)
    operational_shift: Literal["morning", "evening"] | None = None

    @field_validator("plate", "declared_driver_identifier")
    @classmethod
    def strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Il valore è obbligatorio.")
        return value


class ManagedSessionCreateRequest(BaseModel):
    operation_type: Literal["check_out", "check_in"]
    plate: str = Field(min_length=1, max_length=40)
    declared_driver_identifier: str = Field(min_length=1, max_length=120)
    scheduled_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    scheduled_time: str = Field(pattern=r"^\d{2}:\d{2}$")

    @field_validator("plate", "declared_driver_identifier")
    @classmethod
    def strip_managed_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Il valore è obbligatorio.")
        return value


class SharedSessionCreateRequest(BaseModel):
    driver_name: str = Field(min_length=2, max_length=80)
    driver_surname: str = Field(min_length=2, max_length=80)
    vehicle_plate: str = Field(min_length=1, max_length=40)
    procedure_type: Literal["check_out", "check_in"]
    access_token: str | None = Field(default=None, min_length=20, max_length=200)

    @field_validator("driver_name", "driver_surname", "vehicle_plate")
    @classmethod
    def strip_shared_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Il valore è obbligatorio.")
        return value


class WarningCheckRequest(BaseModel):
    odometer_km: int = Field(ge=0)


class CheckpointStartRequest(BaseModel):
    mode: Literal["PHOTO", "VIDEO"]


class EquipmentInput(BaseModel):
    code: Literal["telepass", "phone", "keys", "fuel_card"]
    status: Literal["present", "missing", "damaged"]
    note: str | None = Field(default=None, max_length=500)


class CompleteRequest(BaseModel):
    odometer_km: int
    fuel_percentage: int
    cleanliness_status: Literal[
        "compliant", "non_compliant", "verify"
    ] | None = None
    anomaly_present: bool = False
    anomaly_description: str | None = Field(default=None, max_length=2000)
    operational_note: str | None = Field(default=None, max_length=2000)
    equipment: list[EquipmentInput] = Field(min_length=4, max_length=4)
    client_submission_id: str = Field(min_length=8, max_length=120)
    timezone: str = Field(default="Europe/Rome", max_length=80)
