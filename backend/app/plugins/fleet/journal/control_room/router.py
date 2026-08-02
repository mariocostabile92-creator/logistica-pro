from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse

from app.plugins.fleet.journal.application import service as journal_service
from app.plugins.fleet.journal.control_room import service
from app.plugins.fleet.journal.interfaces.schemas import ManagedSessionCreateRequest
from app.auth.permission_service import has_permission

router = APIRouter(prefix="/api/fleet/journal-control-room", tags=["fleet-journal-control-room"])


@router.post("/sessions", status_code=201)
def create_driver_session(payload: ManagedSessionCreateRequest, request: Request):
    try:
        return journal_service.create_managed_session(payload.model_dump(), request.state.user.organization_id)
    except journal_service.JournalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("")
def procedures(
    request: Request,
    search: str | None = None,
    operation_type: str | None = Query(default=None, pattern="^(check_out|check_in)$"),
    anomaly: str | None = Query(default=None, pattern="^(with|without)$"),
    period: str | None = Query(default=None, pattern="^(today|7d|30d)$"),
    vehicle_id: int | None = Query(default=None, gt=0),
):
    return service.list_procedures({
        "search": search, "operation_type": operation_type, "anomaly": anomaly,
        "period": period, "vehicle_id": vehicle_id,
    }, request.state.user.organization_id, can_delete_media=has_permission(request.state.user.role, "journal:media:delete"),
       current_scope=True)


@router.get("/{procedure_id}")
def procedure(procedure_id: str, request: Request):
    item = service.get_procedure(procedure_id, request.state.user.organization_id,
                                 has_permission(request.state.user.role, "journal:media:delete"))
    if not item:
        raise HTTPException(status_code=404, detail="Procedura Journal non trovata.")
    return item


@router.get("/media/{media_id}")
def media(media_id: str, request: Request, download: bool = False):
    try:
        path, media_type, filename = journal_service.get_admin_media(
            media_id, request.state.user.organization_id
        )
    except journal_service.JournalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    if download:
        return FileResponse(path, media_type=media_type, filename=filename)
    return FileResponse(path, media_type=media_type, headers={"Content-Disposition": "inline"})


@router.delete("/media/{media_id}", status_code=204)
def delete_media(media_id: str, request: Request):
    if not has_permission(request.state.user.role, "journal:media:delete"):
        raise HTTPException(status_code=403, detail="Permesso insufficiente.")
    try:
        journal_service.delete_admin_media(media_id, request.state.user.organization_id)
    except journal_service.JournalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return Response(status_code=204)
