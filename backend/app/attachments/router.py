from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from app.auth.permission_service import has_permission

from app.attachments import service
router = APIRouter(prefix="/api/attachments", tags=["attachments"])


def guarded(call, *args):
    try:
        return call(*args)
    except service.AttachmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("", status_code=201)
async def upload_attachment(
    request: Request,
    entity_type: str = Form(...), entity_id: int = Form(..., gt=0),
    file: UploadFile = File(...), notes: str | None = Form(default=None),
    created_by: str = Form(default="fleet_manager"),
):
    user = request.state.user
    if not has_permission(user.role, "attachments:write"):
        raise HTTPException(status_code=403, detail="Permesso upload allegati insufficiente.")
    content = await file.read()
    return guarded(
        service.upload, entity_type, entity_id, file.filename or "allegato",
        file.content_type or "", content, user.id, notes, user.organization_id,
    )


@router.get("")
def list_attachments(entity_type: str, entity_id: int, request: Request):
    return guarded(service.list_items, entity_type, entity_id, request.state.user.organization_id)


@router.get("/vehicle/{vehicle_id}")
def vehicle_attachments(vehicle_id: int, request: Request):
    return guarded(service.list_vehicle, vehicle_id, request.state.user.organization_id)


@router.get("/{attachment_id}/download")
def download_attachment(attachment_id: str, request: Request):
    item, path = guarded(service.resolve_file, attachment_id, request.state.user.organization_id)
    return FileResponse(
        path,
        media_type=item["mime_type"], filename=item["original_filename"],
    )


@router.get("/{attachment_id}/preview")
def preview_attachment(attachment_id: str, request: Request):
    item, path = guarded(service.resolve_file, attachment_id, request.state.user.organization_id)
    return FileResponse(
        path,
        media_type=item["mime_type"],
        headers={"Content-Disposition": "inline"},
    )


@router.delete("/{attachment_id}", status_code=204)
def delete_attachment(attachment_id: str, request: Request):
    if not has_permission(request.state.user.role, "attachments:write"):
        raise HTTPException(status_code=403, detail="Permesso eliminazione allegati insufficiente.")
    guarded(service.delete, attachment_id, request.state.user.organization_id, request.state.user.id)
    return Response(status_code=204)
