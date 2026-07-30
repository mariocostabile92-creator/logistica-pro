import sqlite3
from decimal import Decimal

from app.plugins.fleet.application.asset_service import AssetNotFoundError, get_asset
from app.plugins.fleet.damage.application import operational_status_service
from app.plugins.fleet.damage.domain.rules import (
    ORIGINS,
    SEVERITIES,
    VEHICLE_STATUSES,
    validate_transition,
)
from app.plugins.fleet.damage.infrastructure import repository
from app.plugins.fleet.journal.infrastructure import repository as journal_repository
from app.plugins.fleet.insurance.application.service import policy_for_vehicle


class DamageError(ValueError):
    status_code = 422


class DamageNotFound(DamageError):
    status_code = 404


class DamageConflict(DamageError):
    status_code = 409


def _money(value) -> str | None:
    if value is None or value == "":
        return None
    amount = Decimal(str(value)).quantize(Decimal("0.01"))
    if amount < 0:
        raise DamageError("Gli importi non possono essere negativi.")
    return format(amount, ".2f")


def _serialize(item):
    if not item:
        return item
    result = dict(item)
    for field in ("estimated_cost", "final_cost"):
        result[field] = _money(result.get(field))
    result["estimated_cost_eur"] = (
        f"€ {Decimal(result['estimated_cost']):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        if result.get("estimated_cost") else None
    )
    result["final_cost_eur"] = (
        f"€ {Decimal(result['final_cost']):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        if result.get("final_cost") else None
    )
    result["events"] = repository.list_events(int(result["id"]))
    asset = get_asset(int(result["vehicle_id"]))
    result.update({
        "operational_status": asset.operational_status,
        "operational_status_reason": asset.operational_status_reason,
        "operational_status_origin": asset.operational_status_origin,
        "operational_status_actor": asset.operational_status_actor,
        "operational_status_updated_at": asset.operational_status_updated_at,
        "operational_status_damage_case_id": asset.operational_status_damage_case_id,
        "asset_profile": asset.profile.model_dump() if asset.profile else None,
        "insurance_policy": policy_for_vehicle(int(result["vehicle_id"])),
    })
    if result.get("source_movement_id"):
        history = journal_repository.asset_history(int(result["vehicle_id"]))
        movement = next(
            (item for item in (history or {}).get("movements", [])
             if item["id"] == result["source_movement_id"]),
            None,
        )
        result["source_movement"] = movement
    else:
        result["source_movement"] = None
    return result


def list_cases(filters):
    return {"items": [_serialize(item) for item in repository.list_cases(filters)]}


def get_case(case_id: int):
    item = repository.get_case(case_id)
    if not item:
        raise DamageNotFound("Pratica danno non trovata.")
    return _serialize(item)


def list_candidates():
    return {"items": repository.candidates()}


def create_case(values: dict[str, object], actor: str):
    origin = str(values["origin"])
    if origin not in ORIGINS:
        raise DamageError("Origine pratica non valida.")
    if str(values["severity"]) not in SEVERITIES:
        raise DamageError("Gravità non valida.")
    vehicle_status = str(values["vehicle_operational_status"])
    if vehicle_status not in VEHICLE_STATUSES:
        raise DamageError("Stato operativo del mezzo non valido.")
    vehicle_status = operational_status_service.normalize(vehicle_status)
    values["vehicle_operational_status"] = vehicle_status
    try:
        get_asset(int(values["vehicle_id"]))
    except AssetNotFoundError as exc:
        raise DamageNotFound("Veicolo non trovato.") from exc
    movement_id = values.get("source_movement_id")
    if origin == "manual":
        if movement_id:
            raise DamageError("Una pratica manuale non può riferire una movimentazione.")
        if not values.get("manual_reason"):
            raise DamageError("La pratica manuale richiede una motivazione.")
    else:
        if not movement_id:
            raise DamageError("La pratica da Journal richiede la movimentazione di origine.")
        if repository.get_by_movement(str(movement_id)):
            raise DamageConflict("Esiste già una pratica per questa anomalia.")
        history = journal_repository.asset_history(int(values["vehicle_id"]))
        movement = next(
            (item for item in (history or {}).get("movements", [])
             if item["id"] == movement_id and item["anomaly_present"]),
            None,
        )
        if not movement:
            raise DamageError("Movimentazione anomala non valida.")
        values["source_document_id"] = f"DOC-{str(movement_id).split('-')[0].upper()}"
        values["declared_driver"] = movement["declared_driver_identifier"]
        values["occurred_at"] = movement["occurred_at"]
        values["description"] = movement["anomaly_description"] or values["description"]
    for field in ("estimated_cost", "final_cost"):
        values[field] = _money(values.get(field))
    try:
        created = repository.create_case(values, actor)
    except sqlite3.IntegrityError as exc:
        raise DamageConflict("Esiste già una pratica per questa anomalia.") from exc
    effective, warning = operational_status_service.automatic_for_severity(
        int(created["id"]), str(values["severity"]), actor,
    )
    if effective is None:
        current_availability = operational_status_service.normalize(
            get_asset(int(values["vehicle_id"])).availability
        )
        effective = operational_status_service.apply(
            case_id=int(created["id"]), requested=current_availability, actor=actor,
            reason="Valutazione iniziale del Fleet Manager",
            origin=f"Pratica {created['case_number']}",
        )
    result = _serialize(repository.get_case(int(created["id"])))
    result["operational_notice"] = warning
    return result


def update_case(case_id: int, changes: dict[str, object], actor: str):
    current = get_case(case_id)
    if "severity" in changes and changes["severity"] not in SEVERITIES:
        raise DamageError("Gravità non valida.")
    if "vehicle_operational_status" in changes:
        status = str(changes["vehicle_operational_status"])
        if status not in VEHICLE_STATUSES:
            raise DamageError("Stato operativo del mezzo non valido.")
        reason = str(changes.pop("operational_reason", "") or "")
        if operational_status_service.normalize(status) != operational_status_service.normalize(
            str(current["vehicle_operational_status"])
        ):
            try:
                operational_status_service.apply(
                    case_id=case_id, requested=status, actor=actor, reason=reason,
                    origin=f"Pratica {current['case_number']}",
                )
            except ValueError as exc:
                raise DamageError(str(exc)) from exc
        changes.pop("vehicle_operational_status", None)
    for field in ("estimated_cost", "final_cost"):
        if field in changes:
            changes[field] = _money(changes[field])
    updated = repository.update_case(case_id, changes, actor)
    notice = None
    if "severity" in changes:
        try:
            _, notice = operational_status_service.automatic_for_severity(
                case_id, str(changes["severity"]), actor,
            )
        except ValueError as exc:
            raise DamageError(str(exc)) from exc
    result = _serialize(repository.get_case(case_id) or updated)
    result["operational_notice"] = notice
    return result


def change_status(
    case_id: int,
    status: str,
    note: str,
    actor: str,
    restoration_status: str | None = None,
):
    current = get_case(case_id)
    try:
        validate_transition(str(current["status"]), status, note)
    except ValueError as exc:
        raise DamageError(str(exc)) from exc
    if status == "chiusa":
        if restoration_status not in VEHICLE_STATUSES:
            raise DamageError(
                "La chiusura richiede una scelta esplicita per lo stato operativo."
            )
    result = repository.change_status(case_id, status, note, actor)
    try:
        operational_status_service.automatic_for_case_status(
            case_id, status, actor, note,
        )
        if status == "chiusa":
            operational_status_service.apply(
                case_id=case_id, requested=str(restoration_status), actor=actor,
                reason=note, origin=f"Chiusura pratica {current['case_number']}",
            )
    except ValueError as exc:
        raise DamageError(str(exc)) from exc
    return _serialize(repository.get_case(case_id) or result)


def add_note(case_id: int, note: str, actor: str):
    if not note.strip():
        raise DamageError("La nota non può essere vuota.")
    events = repository.add_note(case_id, note.strip(), actor)
    if events is None:
        raise DamageNotFound("Pratica danno non trovata.")
    return {"items": events}


def events(case_id: int):
    get_case(case_id)
    return {"items": repository.list_events(case_id)}
