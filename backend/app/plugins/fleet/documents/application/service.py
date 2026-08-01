import json
import uuid

from app.auth import repository as auth_repository
from app.auth.domain import AuthenticatedUser
from app.plugins.fleet.documents.domain.status_evaluator import evaluate_document
from app.plugins.fleet.documents.infrastructure import repository
from app.plugins.fleet.infrastructure import repository as asset_repository


class VehicleDocumentError(Exception):
    status_code = 400


class VehicleDocumentNotFound(VehicleDocumentError):
    status_code = 404


class VehicleDocumentConflict(VehicleDocumentError):
    status_code = 409


def _timezone(user: AuthenticatedUser) -> str:
    organization = auth_repository.organization_by_id(user.organization_id)
    return organization["timezone"] if organization and organization["timezone"] else "Europe/Rome"


def _response(item: dict, user: AuthenticatedUser, include_history: bool = False) -> dict:
    result = evaluate_document(dict(item), _timezone(user))
    result["uploaded_at"] = result.get("attachment_uploaded_at") or result.get("uploaded_at")
    result["contract_link"] = ({"contract_type": result["contract_type"], "contract_number": result.get("contract_number")}
        if result.get("contract_type") and result["document_type"] in {"contratto_noleggio", "contratto_leasing"} else None)
    if include_history:
        result["history"] = repository.events(int(result["id"]), user.organization_id)
    return result


def list_documents(user: AuthenticatedUser, **filters):
    repository.claim_legacy(user.organization_id)
    requested_status = filters.pop("status", None)
    items = [_response(item, user) for item in repository.list_all(organization_id=user.organization_id, **filters)]
    if requested_status:
        items = [item for item in items if item["status"] == requested_status]
    active = [item for item in items if item["status"] != "archiviato"]
    all_items = [_response(item, user) for item in repository.list_all(organization_id=user.organization_id)]
    all_active = [item for item in all_items if item["status"] != "archiviato"]
    documented = {int(item["vehicle_id"]) for item in all_active}
    assets = asset_repository.list_assets()
    summary = {
        "total": len(all_active),
        "complete": sum(item["status"] in {"completo", "senza_scadenza"} for item in all_active),
        "missing_files": sum(not item["has_file"] for item in all_active),
        "expiring": sum(item["status"] == "in_scadenza" for item in all_active),
        "expired": sum(item["status"] == "scaduto" for item in all_active),
        "assets_without_documents": max(0, len(assets) - len(documented)),
    }
    return {"items": active if requested_status != "archiviato" else items, "summary": summary}


def get_document(document_id: int, user: AuthenticatedUser):
    repository.claim_legacy(user.organization_id)
    item = repository.get(document_id, user.organization_id)
    if not item:
        raise VehicleDocumentNotFound("Documento non trovato.")
    return _response(item, user, True)


def create_document(values: dict, user: AuthenticatedUser):
    if not repository.vehicle_exists(int(values["vehicle_id"])):
        raise VehicleDocumentNotFound("Mezzo non trovato.")
    values = {**values, "organization_id": user.organization_id, "status": "mancante"}
    if repository.duplicate_exists(user.organization_id, values):
        raise VehicleDocumentConflict("Esiste gia un documento attivo con gli stessi dati.")
    item = repository.create(values)
    repository.add_event(str(uuid.uuid4()), user.organization_id, int(item["id"]), user.id,
                         "document.created", json.dumps({"title": item["title"]}))
    return _response(item, user, True)


def update_document(document_id: int, values: dict, user: AuthenticatedUser):
    current = repository.get(document_id, user.organization_id)
    if not current:
        raise VehicleDocumentNotFound("Documento non trovato.")
    merged = {**current, **values}
    if repository.duplicate_exists(user.organization_id, merged, document_id):
        raise VehicleDocumentConflict("La modifica produrrebbe un documento duplicato.")
    values.pop("status", None)
    item = repository.update(document_id, user.organization_id, values)
    repository.add_event(str(uuid.uuid4()), user.organization_id, document_id, user.id,
                         "document.updated", json.dumps(sorted(values)))
    return _response(item, user, True)


def archive_document(document_id: int, user: AuthenticatedUser):
    if not repository.get(document_id, user.organization_id):
        raise VehicleDocumentNotFound("Documento non trovato.")
    item = repository.archive(document_id, user.organization_id)
    repository.add_event(str(uuid.uuid4()), user.organization_id, document_id, user.id, "document.archived")
    return _response(item, user, True)
