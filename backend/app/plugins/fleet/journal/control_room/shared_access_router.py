from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.plugins.fleet.journal.application import shared_access_service
from app.plugins.fleet.journal.control_room.shared_access_schemas import (
    SharedAccessCreateRequest,
)


router = APIRouter(tags=["fleet-journal-shared-access"])
JOURNAL_PAGE = Path(__file__).resolve().parents[6] / "frontend" / "journal" / "index.html"


def _guard(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except shared_access_service.SharedAccessError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/api/fleet/journal-control-room/shared-access", status_code=201)
def create_shared_access(request: SharedAccessCreateRequest):
    return _guard(shared_access_service.create, request.regenerate)


@router.get("/api/fleet/journal-control-room/shared-access/active")
def active_shared_access():
    return {"item": shared_access_service.get_active()}


@router.post("/api/fleet/journal-control-room/shared-access/{access_id}/revoke")
def revoke_shared_access(access_id: str):
    return _guard(shared_access_service.revoke, access_id)


@router.get("/api/plugins/fleet/v1/journal/shared-access/{token}")
def validate_shared_access(token: str):
    return _guard(shared_access_service.validate, token)


@router.get("/app/journal/access/{token}", include_in_schema=False)
def shared_access_page(token: str):
    return FileResponse(JOURNAL_PAGE)

