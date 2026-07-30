from app.plugins.fleet.documents.infrastructure import repository
from app.plugins.fleet.infrastructure import repository as asset_repository


class VehicleDocumentError(Exception):
    status_code = 400


class VehicleDocumentNotFound(VehicleDocumentError):
    status_code = 404


def _response(item: dict[str, object]) -> dict[str, object]:
    item["has_file"] = bool(item.get("file_reference"))
    item["contract_link"] = (
        {
            "contract_type": item["contract_type"],
            "contract_number": item.get("contract_number"),
        }
        if item.get("contract_type")
        and item["document_type"] in {"contratto_noleggio", "contratto_leasing"}
        else None
    )
    return item


def list_documents(**filters):
    items = [_response(item) for item in repository.list_all(**filters)]
    assets = asset_repository.list_assets()
    return {
        "items": items,
        "summary": repository.fleet_summary(len(assets)),
    }


def get_document(document_id: int):
    item = repository.get(document_id)
    if not item:
        raise VehicleDocumentNotFound("Documento non trovato.")
    return _response(item)


def create_document(values: dict[str, object], actor: str):
    if not repository.vehicle_exists(int(values["vehicle_id"])):
        raise VehicleDocumentNotFound("Mezzo non trovato.")
    return _response(repository.create(values))


def update_document(document_id: int, values: dict[str, object], actor: str):
    item = repository.update(document_id, values)
    if not item:
        raise VehicleDocumentNotFound("Documento non trovato.")
    return _response(item)
