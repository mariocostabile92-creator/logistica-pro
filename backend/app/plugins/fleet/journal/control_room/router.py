from fastapi import APIRouter, HTTPException, Query

from app.plugins.fleet.journal.control_room import service

router = APIRouter(prefix="/api/fleet/journal-control-room", tags=["fleet-journal-control-room"])


@router.get("")
def procedures(
    search: str | None = None,
    operation_type: str | None = Query(default=None, pattern="^(check_out|check_in)$"),
    anomaly: str | None = Query(default=None, pattern="^(with|without)$"),
    period: str | None = Query(default=None, pattern="^(today|7d|30d)$"),
    vehicle_id: int | None = Query(default=None, gt=0),
):
    return service.list_procedures({
        "search": search, "operation_type": operation_type, "anomaly": anomaly,
        "period": period, "vehicle_id": vehicle_id,
    })


@router.get("/{procedure_id}")
def procedure(procedure_id: str):
    item = service.get_procedure(procedure_id)
    if not item:
        raise HTTPException(status_code=404, detail="Procedura Journal non trovata.")
    return item
