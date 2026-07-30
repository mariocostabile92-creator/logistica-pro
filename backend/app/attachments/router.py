from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse

from app.attachments import service
from app.attachments.storage import attachment_storage


router = APIRouter(prefix="/api/attachments", tags=["attachments"])


def guarded(call, *args):
    try:
        return call(*args)
    except service.AttachmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("", status_code=201)
async def upload_attachment(
    entity_type: str = Form(...), entity_id: int = Form(..., gt=0),
    file: UploadFile = File(...), notes: str | None = Form(default=None),
    created_by: str = Form(default="fleet_manager"),
):
    content = await file.read()
    return guarded(
        service.upload, entity_type, entity_id, file.filename or "allegato",
        file.content_type or "", content, created_by, notes,
    )


@router.get("")
def list_attachments(entity_type: str, entity_id: int):
    return guarded(service.list_items, entity_type, entity_id)


@router.get("/vehicle/{vehicle_id}")
def vehicle_attachments(vehicle_id: int):
    return guarded(service.list_vehicle, vehicle_id)


@router.get("/{attachment_id}/download")
def download_attachment(attachment_id: str):
    item = guarded(service.get, attachment_id)
    return FileResponse(
        attachment_storage.resolve(item["storage_path"]),
        media_type=item["mime_type"], filename=item["original_filename"],
    )


@router.get("/{attachment_id}/preview")
def preview_attachment(attachment_id: str):
    item = guarded(service.get, attachment_id)
    return FileResponse(
        attachment_storage.resolve(item["storage_path"]),
        media_type=item["mime_type"],
        headers={"Content-Disposition": "inline"},
    )


@router.delete("/{attachment_id}", status_code=204)
def delete_attachment(attachment_id: str):
    guarded(service.delete, attachment_id)
    return Response(status_code=204)
