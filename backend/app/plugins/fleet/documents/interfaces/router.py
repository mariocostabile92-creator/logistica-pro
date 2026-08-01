from fastapi import APIRouter, HTTPException, Query, Request, status
from app.auth.permission_service import has_permission

from app.plugins.fleet.documents.application import service
from app.plugins.fleet.documents.interfaces.schemas import (
    DOCUMENT_STATUSES,
    DOCUMENT_TYPES,
    VehicleDocumentRequest,
    VehicleDocumentUpdateRequest,
)

router = APIRouter(prefix="/api/fleet/documents", tags=["fleet-documents"])


def guarded(call, *args, **kwargs):
    try:
        return call(*args, **kwargs)
    except service.VehicleDocumentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def permitted(request: Request, permission: str):
    user = request.state.user
    if not has_permission(user.role, permission):
        raise HTTPException(status_code=403, detail="Permesso insufficiente per il workspace Documenti.")
    return user


@router.get("")
def documents(
    request: Request,
    vehicle_id: int | None = Query(default=None, gt=0),
    search: str | None = Query(default=None, max_length=240),
    status_filter: str | None = Query(default=None, alias="status"),
    document_type: str | None = None,
    has_file: bool | None = None,
):
    if status_filter and status_filter not in DOCUMENT_STATUSES:
        raise HTTPException(status_code=422, detail="Stato documento non supportato.")
    if document_type and document_type not in DOCUMENT_TYPES:
        raise HTTPException(status_code=422, detail="Tipologia documento non supportata.")
    return guarded(
        service.list_documents,
        permitted(request, "documents:read"),
        vehicle_id=vehicle_id,
        search=search,
        status=status_filter,
        document_type=document_type,
        has_file=has_file,
    )


@router.get("/{document_id}")
def document(document_id: int, request: Request):
    return guarded(service.get_document, document_id, permitted(request, "documents:read"))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_document(payload: VehicleDocumentRequest, request: Request):
    return guarded(service.create_document, payload.model_dump(mode="json"), permitted(request, "documents:write"))


@router.patch("/{document_id}")
def update_document(document_id: int, payload: VehicleDocumentUpdateRequest, request: Request):
    return guarded(service.update_document, document_id, payload.model_dump(exclude_unset=True, mode="json"), permitted(request, "documents:write"))


@router.post("/{document_id}/archive")
def archive_document(document_id: int, request: Request):
    return guarded(service.archive_document, document_id, permitted(request, "documents:archive"))
