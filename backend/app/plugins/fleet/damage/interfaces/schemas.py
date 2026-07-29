from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


def required(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("Il valore non può essere vuoto.")
    return text


class DamageCreateRequest(BaseModel):
    vehicle_id: int = Field(gt=0)
    source_movement_id: str | None = None
    declared_driver: str | None = None
    occurred_at: datetime
    origin: str
    manual_reason: str | None = None
    description: str = Field(min_length=1, max_length=4000)
    severity: str = "media"
    vehicle_operational_status: str = "disponibile"
    repair_shop: str | None = None
    estimated_cost: Decimal | None = Field(default=None, ge=0)
    final_cost: Decimal | None = Field(default=None, ge=0)
    actor: str = "fleet_manager"

    _description = field_validator("description")(required)
    _actor = field_validator("actor")(required)


class DamageUpdateRequest(BaseModel):
    description: str | None = Field(default=None, max_length=4000)
    severity: str | None = None
    vehicle_operational_status: str | None = None
    operational_reason: str | None = Field(default=None, max_length=2000)
    repair_shop: str | None = None
    estimated_cost: Decimal | None = Field(default=None, ge=0)
    final_cost: Decimal | None = Field(default=None, ge=0)
    actor: str = "fleet_manager"


class DamageStatusRequest(BaseModel):
    status: str
    note: str = Field(min_length=1, max_length=2000)
    restoration_status: str | None = None
    actor: str = "fleet_manager"


class DamageNoteRequest(BaseModel):
    note: str = Field(min_length=1, max_length=2000)
    actor: str = "fleet_manager"


class ManualOperationalStatusRequest(BaseModel):
    status: str
    reason: str = Field(min_length=1, max_length=2000)
    origin: str
    actor: str = "fleet_manager"
    override_restriction: bool = False

    _reason = field_validator("reason")(required)
    _actor = field_validator("actor")(required)
