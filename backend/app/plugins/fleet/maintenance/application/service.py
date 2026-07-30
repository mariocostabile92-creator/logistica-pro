import sqlite3

from app.plugins.fleet.application.asset_service import AssetNotFoundError, get_asset
from app.plugins.fleet.damage.application.service import DamageNotFound, get_case
from app.plugins.fleet.maintenance.infrastructure import repository


TYPES = {
    "tagliando", "pneumatici", "revisione", "freni", "meccanica",
    "carrozzeria", "elettrico", "altro",
}
STATUSES = {"aperta", "programmata", "in_lavorazione", "completata", "annullata"}
PRIORITIES = {"bassa", "media", "alta", "critica"}


class MaintenanceError(ValueError):
    status_code = 422


class MaintenanceNotFound(MaintenanceError):
    status_code = 404


class MaintenanceConflict(MaintenanceError):
    status_code = 409


def _serialize(item):
    if not item:
        return item
    result = dict(item)
    result["events"] = repository.list_events(int(result["id"]))
    return result


def list_maintenances(vehicle_id: int | None = None):
    items = [_serialize(item) for item in repository.list_all(vehicle_id)]
    return {
        "items": items,
        "summary": {
            "open": sum(item["status"] in {"aperta", "programmata", "in_lavorazione"} for item in items),
            "in_workshop": len({
                item["vehicle_id"] for item in items if item["status"] == "in_lavorazione"
            }),
            "scheduled": sum(item["status"] == "programmata" for item in items),
            "completed": sum(item["status"] == "completata" for item in items),
        },
    }


def get_maintenance(maintenance_id: int):
    item = repository.get(maintenance_id)
    if not item:
        raise MaintenanceNotFound("Manutenzione non trovata.")
    return _serialize(item)


def create_maintenance(values: dict[str, object], actor: str):
    if values["maintenance_type"] not in TYPES:
        raise MaintenanceError("Tipologia manutenzione non valida.")
    if values.get("status", "aperta") not in STATUSES:
        raise MaintenanceError("Stato manutenzione non valido.")
    if values.get("priority", "media") not in PRIORITIES:
        raise MaintenanceError("Priorità manutenzione non valida.")
    damage_case_id = values.get("damage_case_id")
    if damage_case_id:
        damage = get_case(int(damage_case_id))
        if repository.get_by_damage_case(int(damage_case_id)):
            raise MaintenanceConflict(
                "La pratica danno ha già generato una manutenzione."
            )
        values["vehicle_id"] = damage["vehicle_id"]
        values["description"] = damage["description"]
        values["repair_shop"] = values.get("repair_shop") or damage.get("repair_shop")
    try:
        get_asset(int(values["vehicle_id"]))
    except AssetNotFoundError as exc:
        raise MaintenanceNotFound("Mezzo non trovato.") from exc
    try:
        return _serialize(repository.create(values, actor))
    except sqlite3.IntegrityError as exc:
        raise MaintenanceConflict("Manutenzione già presente.") from exc


def update_maintenance(
    maintenance_id: int,
    changes: dict[str, object],
    actor: str,
):
    if "maintenance_type" in changes and changes["maintenance_type"] not in TYPES:
        raise MaintenanceError("Tipologia manutenzione non valida.")
    if "status" in changes and changes["status"] not in STATUSES:
        raise MaintenanceError("Stato manutenzione non valido.")
    if "priority" in changes and changes["priority"] not in PRIORITIES:
        raise MaintenanceError("Priorità manutenzione non valida.")
    updated = repository.update(maintenance_id, changes, actor)
    if not updated:
        raise MaintenanceNotFound("Manutenzione non trovata.")
    return _serialize(updated)
