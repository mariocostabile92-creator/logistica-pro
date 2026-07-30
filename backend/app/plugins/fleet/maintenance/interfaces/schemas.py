from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def required(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("Il valore non può essere vuoto.")
    return text


class MaintenanceCreateRequest(BaseModel):
    vehicle_id: int | None = Field(default=None, gt=0)
    damage_case_id: int | None = Field(default=None, gt=0)
    description: str = Field(min_length=1, max_length=4000)
    maintenance_type: str
    status: str = "aperta"
    priority: str = "media"
    repair_shop: str | None = Field(default=None, max_length=300)
    opened_at: datetime | None = None
    expected_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=4000)
    actor: str = "fleet_manager"

    _description = field_validator("description")(required)
    _actor = field_validator("actor")(required)


class MaintenanceUpdateRequest(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=4000)
    maintenance_type: str | None = None
    status: str | None = None
    priority: str | None = None
    repair_shop: str | None = Field(default=None, max_length=300)
    expected_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=4000)
    actor: str = "fleet_manager"
