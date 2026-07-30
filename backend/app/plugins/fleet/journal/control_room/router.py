from fastapi import APIRouter, HTTPException, Query

from app.plugins.fleet.journal.application import service as journal_service
from app.plugins.fleet.journal.control_room import service
from app.plugins.fleet.journal.interfaces.schemas import ManagedSessionCreateRequest

router = APIRouter(prefix="/api/fleet/journal-control-room", tags=["fleet-journal-control-room"])


@router.post("/sessions", status_code=201)
def create_driver_session(request: ManagedSessionCreateRequest):
    try:
        return journal_service.create_managed_session(request.model_dump())
    except journal_service.JournalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


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
