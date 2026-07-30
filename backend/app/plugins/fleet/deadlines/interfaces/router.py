from fastapi import APIRouter, Query

from app.plugins.fleet.deadlines.application.service import list_deadlines

router = APIRouter(prefix="/api/fleet/deadlines", tags=["fleet-deadlines"])


@router.get("")
def deadlines(vehicle_id: int | None = Query(default=None, gt=0)):
    return list_deadlines(vehicle_id)
