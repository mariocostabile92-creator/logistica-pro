from fastapi import APIRouter, HTTPException, Query, status

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


@router.get("")
def documents(
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
        vehicle_id=vehicle_id,
        search=search,
        status=status_filter,
        document_type=document_type,
        has_file=has_file,
    )


@router.get("/{document_id}")
def document(document_id: int):
    return guarded(service.get_document, document_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_document(request: VehicleDocumentRequest):
    values = request.model_dump(mode="json")
    actor = str(values.pop("actor"))
    return guarded(service.create_document, values, actor)


@router.patch("/{document_id}")
def update_document(document_id: int, request: VehicleDocumentUpdateRequest):
    values = request.model_dump(exclude_unset=True, mode="json")
    actor = str(values.pop("actor", "fleet_manager"))
    return guarded(service.update_document, document_id, values, actor)
