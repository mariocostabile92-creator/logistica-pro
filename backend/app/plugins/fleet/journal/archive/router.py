from fastapi import APIRouter, HTTPException, Query, Request

from app.plugins.fleet.journal.archive import service
from app.auth.permission_service import has_permission


router = APIRouter(prefix="/api/fleet/journal-archive", tags=["fleet-journal-archive"])


@router.get("/month")
def month(request: Request, month: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")):
    try:
        return service.month_snapshot(month, request.state.user.organization_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Mese non valido.") from exc


@router.get("/day")
def day(
    request: Request,
    date: str,
    search: str | None = None,
    operation_type: str | None = Query(default=None, pattern="^(check_out|check_in)$"),
    status: str | None = None,
    anomaly: str | None = Query(default=None, pattern="^(with|without)$"),
    media: str | None = Query(default=None, pattern="^(with|without)$"),
    vehicle_id: int | None = None,
    plate: str | None = None,
    driver: str | None = None,
):
    try:
        return service.day_snapshot(date, request.state.user.organization_id, {
            "search": search, "operation_type": operation_type, "status": status,
            "anomaly": anomaly, "media": media, "vehicle_id": vehicle_id,
            "plate": plate, "driver": driver,
        }, has_permission(request.state.user.role, "journal:media:delete"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Data non valida.") from exc
