from typing import Literal

from pydantic import BaseModel, Field


FleetCapacityStatus = Literal[
    "SUFFICIENT",
    "SHORTAGE",
    "NEED_NOT_DETERMINABLE",
]

VehicleNeedStatus = Literal[
    "COMPLETE",
    "PARTIAL",
    "NOT_CONFIGURED",
]


class DailyFleetCapacitySnapshot(BaseModel):
    operational_date: str
    requested_station: str | None = None
    station_scope_applied: bool = False
    total_vehicles: int = Field(ge=0)
    available_vehicles: int = Field(ge=0)
    unavailable_vehicles: int = Field(ge=0)
    maintenance_vehicles: int = Field(ge=0)
    blocked_vehicles: int = Field(ge=0)
    unknown_vehicles: int = Field(ge=0)
    vehicle_need: int | None = Field(default=None, ge=0)
    vehicle_need_rule: str | None = None
    vehicle_need_status: VehicleNeedStatus = "NOT_CONFIGURED"
    effective_requirement_buckets: list[str] = Field(default_factory=list)
    missing_requirement_buckets: list[str] = Field(default_factory=list)
    margin: int | None = None
    capacity_status: FleetCapacityStatus
    capacity_message: str
    route_assignments_available: bool = False
    assigned_vehicles: int | None = Field(default=None, ge=0)
    routes_without_vehicle: int | None = Field(default=None, ge=0)
    source: str = "FLEET_ASSET_REGISTRY"
    date_semantics: Literal["CURRENT_OPERATIONAL_STATE"] = (
        "CURRENT_OPERATIONAL_STATE"
    )
    observed_at: str | None = None
