import hmac

from fastapi import (
    APIRouter,
    File,
    Header,
    HTTPException,
    Response,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse

from app.core.config import SETTINGS
from app.plugins.fleet.journal.application import service
from app.plugins.fleet.journal.interfaces.schemas import (
    CompleteRequest,
    SessionCreateRequest,
    SharedSessionCreateRequest,
    WarningCheckRequest,
)


router = APIRouter(
    prefix="/api/plugins/fleet/v1/journal",
    tags=["fleet-journal-v1"],
)


def guarded(call, *args):
    try:
        return call(*args)
    except service.JournalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/configuration")
def get_configuration():
    return service.configuration()


@router.get("/assets")
def assets(access_token: str, plate: str | None = None):
    try:
        access = service.shared_access_service.validate(access_token)
    except service.shared_access_service.SharedAccessError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    organization_id = str(access["organization_id"])
    if plate is None:
        return guarded(service.list_assets, organization_id)
    return guarded(service.find_asset, plate, organization_id)


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def create_session(request: SessionCreateRequest):
    return guarded(service.create_session, request.model_dump())


@router.post("/sessions/shared", status_code=status.HTTP_201_CREATED)
def create_shared_session(payload: SharedSessionCreateRequest, request: Request):
    values = payload.model_dump()
    harness_token = getattr(request.app.state, "test_auth_harness_token", None)
    supplied_token = request.headers.get("X-Test-Auth-Harness", "")
    values["_test_harness_authorized"] = bool(
        SETTINGS.environment == "test"
        and harness_token
        and supplied_token
        and hmac.compare_digest(supplied_token, harness_token)
        and request.headers.get("X-Auth-Enforce") != "1"
    )
    return guarded(service.create_shared_session, values)


@router.get("/sessions/{session_id}")
def open_shared_session(session_id: str):
    return guarded(service.open_managed_session, session_id)


@router.post("/sessions/{session_id}/progress")
def session_progress(
    session_id: str,
    x_journal_token: str | None = Header(default=None),
):
    return guarded(
        service.mark_managed_session_in_progress,
        session_id,
        x_journal_token,
    )


@router.post("/sessions/{session_id}/warnings")
def session_warnings(
    session_id: str,
    request: WarningCheckRequest,
    x_journal_token: str | None = Header(default=None),
):
    return guarded(
        service.check_session_warnings,
        session_id,
        x_journal_token,
        request.odometer_km,
    )


@router.post("/sessions/{session_id}/media", status_code=status.HTTP_201_CREATED)
async def upload_media(
    session_id: str,
    file: UploadFile = File(...),
    x_journal_token: str | None = Header(default=None),
):
    data = await file.read(service.MAX_MEDIA_BYTES + 1)
    return guarded(
        service.add_media,
        session_id,
        x_journal_token,
        file.filename or "photo",
        file.content_type,
        data,
    )


@router.delete("/sessions/{session_id}/media/{media_id}", status_code=204)
def remove_media(
    session_id: str,
    media_id: str,
    x_journal_token: str | None = Header(default=None),
):
    guarded(service.delete_media, session_id, media_id, x_journal_token)
    return Response(status_code=204)


@router.post("/sessions/{session_id}/complete")
def complete_session(
    session_id: str,
    request: CompleteRequest,
    x_journal_token: str | None = Header(default=None),
):
    return guarded(
        service.complete,
        session_id,
        x_journal_token,
        request.model_dump(),
    )


@router.get("/movements/{movement_id}/receipt")
def movement_receipt(movement_id: str):
    return guarded(service.receipt, movement_id)


@router.get("/vehicles/{asset_id}/history")
def vehicle_history(asset_id: int, request: Request):
    return guarded(service.vehicle_history, asset_id, request.state.user.organization_id)


@router.get("/media/{media_id}")
def movement_media(media_id: str, token: str | None = None, x_journal_token: str | None = Header(default=None)):
    path, media_type = guarded(service.get_movement_media, media_id, token or x_journal_token)
    return FileResponse(path, media_type=media_type)
