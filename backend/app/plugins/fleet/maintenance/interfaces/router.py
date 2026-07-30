from fastapi import APIRouter, HTTPException, Query, status

from app.plugins.fleet.maintenance.application import service
from app.plugins.fleet.maintenance.interfaces.schemas import (
    MaintenanceCreateRequest,
    MaintenanceUpdateRequest,
)

router = APIRouter(prefix="/api/fleet/maintenances", tags=["fleet-maintenance"])


def guarded(call, *args):
    try:
        return call(*args)
    except service.MaintenanceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("")
def maintenances(vehicle_id: int | None = Query(default=None, gt=0)):
    return guarded(service.list_maintenances, vehicle_id)


@router.get("/{maintenance_id}")
def maintenance(maintenance_id: int):
    return guarded(service.get_maintenance, maintenance_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_maintenance(request: MaintenanceCreateRequest):
    values = request.model_dump(mode="json")
    actor = str(values.pop("actor"))
    if not values.get("vehicle_id") and not values.get("damage_case_id"):
        raise HTTPException(
            status_code=422,
            detail="Indicare un mezzo o una pratica danno.",
        )
    return guarded(service.create_maintenance, values, actor)


@router.patch("/{maintenance_id}")
def update_maintenance(
    maintenance_id: int,
    request: MaintenanceUpdateRequest,
):
    values = request.model_dump(exclude_unset=True, mode="json")
    actor = str(values.pop("actor", "fleet_manager"))
    return guarded(service.update_maintenance, maintenance_id, values, actor)
