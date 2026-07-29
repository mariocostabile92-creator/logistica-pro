from fastapi import (
    APIRouter,
    File,
    Header,
    HTTPException,
    Response,
    UploadFile,
    status,
)

from app.plugins.fleet.journal.application import service
from app.plugins.fleet.journal.interfaces.schemas import (
    CompleteRequest,
    SessionCreateRequest,
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
def asset_by_plate(plate: str):
    return guarded(service.find_asset, plate)


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def create_session(request: SessionCreateRequest):
    return guarded(service.create_session, request.model_dump())


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
