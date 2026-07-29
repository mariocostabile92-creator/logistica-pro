from pydantic import BaseModel


class PatchAssignmentRequest(BaseModel):
    driver_id: str | None = None
    driver_name: str | None = None
    vehicle_id: str | None = None
    plate: str | None = None
    remove_driver: bool = False
    remove_vehicle: bool = False
    confirm: bool | None = None
    manual_override: bool = True
    note: str | None = None
    allow_cross_station: bool = False
    actor: str = "local_operator"
