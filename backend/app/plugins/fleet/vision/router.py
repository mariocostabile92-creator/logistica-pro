from fastapi import APIRouter, Query

from app.plugins.fleet.vision.service import fleet_vision

router = APIRouter(prefix="/api/fleet/vision", tags=["fleet-vision"])


@router.get("")
def vision(vehicle_id: int | None = Query(default=None, gt=0)):
    return fleet_vision(vehicle_id)
