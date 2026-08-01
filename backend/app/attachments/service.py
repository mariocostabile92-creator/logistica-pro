import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.attachments import repository
from app.attachments.domain import (
    SUPPORTED_ENTITY_TYPES, SUPPORTED_EXTENSIONS, SUPPORTED_MIME_TYPES,
)
from app.attachments.storage import attachment_storage
from app.core.config import MAX_UPLOAD_SIZE_BYTES


class AttachmentError(ValueError):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


def _present(item: dict) -> dict:
    result = dict(item)
    result["preview_available"] = bool(item["preview_available"])
    result["download_url"] = f"/api/attachments/{item['id']}/download"
    result["preview_url"] = (
        f"/api/attachments/{item['id']}/preview"
        if result["preview_available"] else None
    )
    return result


def _validate(entity_type: str, filename: str, mime_type: str, content: bytes) -> str:
    if entity_type not in SUPPORTED_ENTITY_TYPES:
        raise AttachmentError("Tipo entità allegato non supportato.")
    suffix = Path(filename).suffix.lower()
    if entity_type == "document" and suffix in {".mp4", ".mov"}:
        raise AttachmentError("Il modulo Documenti accetta PDF e immagini, non video.")
    if suffix not in SUPPORTED_EXTENSIONS:
        raise AttachmentError("Formato file non supportato.")
    if not content:
        raise AttachmentError("Il file è vuoto.")
    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise AttachmentError("Il file supera la dimensione massima consentita.", 413)
    detected = mime_type or mimetypes.guess_type(filename)[0] or ""
    if detected not in SUPPORTED_MIME_TYPES:
        raise AttachmentError("Tipo MIME non supportato.")
    signatures = {
        ".pdf": content.startswith(b"%PDF"),
        ".jpg": content.startswith(b"\xff\xd8\xff"),
        ".jpeg": content.startswith(b"\xff\xd8\xff"),
        ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        ".webp": content.startswith(b"RIFF") and content[8:12] == b"WEBP",
        ".mp4": len(content) > 12 and content[4:8] == b"ftyp",
        ".mov": len(content) > 12 and content[4:8] == b"ftyp",
    }
    if not signatures.get(suffix, False):
        raise AttachmentError("Il contenuto non corrisponde al formato dichiarato.")
    return detected


def upload(
    entity_type: str, entity_id: int, filename: str, mime_type: str,
    content: bytes, created_by: str, notes: str | None,
    organization_id: str | None = None,
) -> dict:
    if entity_type not in SUPPORTED_ENTITY_TYPES:
        raise AttachmentError("Tipo entità allegato non supportato.")
    if not repository.entity_exists(entity_type, entity_id):
        raise AttachmentError("Entità collegata non trovata.", 404)
    _authorize_document(entity_type, entity_id, organization_id)
    safe_name = Path(filename or "allegato").name
    verified_mime = _validate(entity_type, safe_name, mime_type, content)
    attachment_id = str(uuid.uuid4())
    stored_filename = f"{attachment_id}{Path(safe_name).suffix.lower()}"
    storage_path = attachment_storage.save(stored_filename, content)
    try:
        item = repository.create({
            "id": attachment_id, "entity_type": entity_type,
            "entity_id": entity_id, "original_filename": safe_name,
            "stored_filename": stored_filename, "mime_type": verified_mime,
            "size": len(content), "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": created_by.strip() or "fleet_manager",
            "storage_path": storage_path, "preview_available": True,
            "notes": notes.strip() if notes else None,
        })
    except Exception:
        attachment_storage.delete(storage_path)
        raise
    if entity_type == "document" and organization_id:
        from app.plugins.fleet.documents.infrastructure import repository as document_repository
        document_repository.add_event(
            str(uuid.uuid4()), organization_id, entity_id, created_by,
            "attachment.added", safe_name,
        )
    return _present(item)


def _authorize_document(entity_type: str, entity_id: int, organization_id: str | None) -> None:
    if entity_type == "document" and repository.document_organization_id(entity_id) != organization_id:
        raise AttachmentError("Allegato non trovato.", 404)


def get(attachment_id: str, organization_id: str | None = None) -> dict:
    item = repository.get(attachment_id)
    if not item:
        raise AttachmentError("Allegato non trovato.", 404)
    _authorize_document(item["entity_type"], int(item["entity_id"]), organization_id)
    return item


def list_items(entity_type: str, entity_id: int, organization_id: str | None = None) -> dict:
    if entity_type not in SUPPORTED_ENTITY_TYPES:
        raise AttachmentError("Tipo entità allegato non supportato.")
    _authorize_document(entity_type, entity_id, organization_id)
    items = [_present(item) for item in repository.list_for_entity(entity_type, entity_id)]
    return {"items": items, "count": len(items)}


def list_vehicle(vehicle_id: int) -> dict:
    items = [_present(item) for item in repository.list_for_vehicle(vehicle_id)]
    return {"items": items, "count": len(items)}


def delete(attachment_id: str, organization_id: str | None = None, actor_user_id: str = "system") -> None:
    item = get(attachment_id, organization_id)
    attachment_storage.delete(item["storage_path"])
    repository.delete(attachment_id)
    if item["entity_type"] == "document" and organization_id:
        from app.plugins.fleet.documents.infrastructure import repository as document_repository
        document_repository.add_event(
            str(uuid.uuid4()), organization_id, int(item["entity_id"]), actor_user_id,
            "attachment.removed", item["original_filename"],
        )
