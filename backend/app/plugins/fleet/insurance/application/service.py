import sqlite3
from decimal import Decimal

from app.plugins.fleet.insurance.infrastructure import repository


class InsuranceError(ValueError):
    status_code = 422


class InsuranceNotFound(InsuranceError):
    status_code = 404


class InsuranceConflict(InsuranceError):
    status_code = 409


def _money(value) -> str | None:
    if value is None or value == "":
        return None
    return format(Decimal(str(value)).quantize(Decimal("0.01")), ".2f")


def _serialize(item):
    if not item:
        return item
    result = dict(item)
    result["coverage_limit"] = _money(result.get("coverage_limit"))
    result["insurance_deductible"] = _money(result.get("insurance_deductible"))
    return result


def list_policies(vehicle_id: int | None = None):
    items = [_serialize(item) for item in repository.list_all(vehicle_id)]
    return {
        "items": items,
        "summary": {
            "total": len(items),
            "active": sum(item["status"] == "attiva" for item in items),
            "expiring": sum(item["status"] == "in_scadenza" for item in items),
            "expired": sum(item["status"] == "scaduta" for item in items),
            "suspended": sum(item["status"] == "sospesa" for item in items),
        },
    }


def get_policy(policy_id: int):
    item = repository.get(policy_id)
    if not item:
        raise InsuranceNotFound("Polizza assicurativa non trovata.")
    return _serialize(item)


def policy_for_vehicle(vehicle_id: int):
    return _serialize(repository.get_by_vehicle(vehicle_id))


def create_policy(values: dict[str, object], actor: str):
    if not repository.vehicle_exists(int(values["vehicle_id"])):
        raise InsuranceNotFound("Mezzo non trovato.")
    values["coverage_limit"] = _money(values.get("coverage_limit"))
    values["insurance_deductible"] = _money(values.get("insurance_deductible"))
    try:
        return _serialize(repository.create(values))
    except sqlite3.IntegrityError as exc:
        raise InsuranceConflict(
            "Il mezzo o il numero polizza è già associato a una polizza."
        ) from exc


def update_policy(policy_id: int, changes: dict[str, object], actor: str):
    for field in ("coverage_limit", "insurance_deductible"):
        if field in changes:
            changes[field] = _money(changes[field])
    try:
        item = repository.update(policy_id, changes)
    except sqlite3.IntegrityError as exc:
        raise InsuranceConflict("Numero polizza già utilizzato.") from exc
    if not item:
        raise InsuranceNotFound("Polizza assicurativa non trovata.")
    return _serialize(item)
