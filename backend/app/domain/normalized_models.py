from pydantic import BaseModel, Field


class NormalizedPlanningRow(BaseModel):
    row_number: int
    driver_name: str | None = None
    driver_key: str | None = None
    vehicle_plate: str | None = None
    station: str | None = None
    route: str | None = None
    cycle: str | None = None
    raw: dict[str, object] = Field(default_factory=dict)


class NormalizedFleetRow(BaseModel):
    row_number: int
    vehicle_plate: str | None = None
    driver_name: str | None = None
    driver_key: str | None = None
    second_driver_name: str | None = None
    second_driver_key: str | None = None
    status: str | None = None
    station: str | None = None
    workshop: str | None = None
    notes: str | None = None
    key_available: str | None = None
    fuel_card: str | None = None
    vehicle_model: str | None = None
    expirations: str | None = None
    raw: dict[str, object] = Field(default_factory=dict)


class OperationConflict(BaseModel):
    code: str
    severity: str
    message: str
    reason: str | None = None
    entity_ref: str
    row_number: int | None = None
    suggested_action: str | None = None
