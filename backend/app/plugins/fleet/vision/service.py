from collections import defaultdict
from datetime import date, datetime

from app.plugins.fleet.deadlines.application.service import list_deadlines
from app.plugins.fleet.vision import repository


OPEN_DAMAGE = {
    "nuova", "in_valutazione", "preventivo_richiesto", "preventivo_ricevuto",
    "riparazione_programmata", "in_riparazione",
}
OPEN_MAINTENANCE = {"aperta", "programmata", "in_lavorazione"}
OPEN_FRANCHISE = {"da_valutare", "in_verifica", "applicata"}
ACTIVE_RENTAL = {"attivo", "prorogato"}
OPERATIVE = {"disponibile", "disponibile_con_limitazioni", "available", "reserve"}
UNAVAILABLE = {"indisponibile", "unavailable"}
MAINTENANCE = {"in_manutenzione", "in_officina", "maintenance", "workshop"}


def _group(rows: list[dict]) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[int(row["vehicle_id"])].append(row)
    return grouped


def _event(
    source: str,
    source_id: object,
    occurred_at: str | None,
    event_type: str,
    label: str,
    module: str,
) -> dict | None:
    if not occurred_at:
        return None
    return {
        "id": f"{source}:{source_id}:{event_type}",
        "source": source,
        "source_id": source_id,
        "occurred_at": occurred_at,
        "event_type": event_type,
        "label": label,
        "module": module,
    }


def _timeline(
    asset_id: int,
    movements: list[dict],
    damages: list[dict],
    maintenances: list[dict],
    rentals: list[dict],
    documents: list[dict],
    franchises: list[dict],
    status_event: dict | None,
) -> list[dict]:
    events = []
    for row in movements:
        events.append(_event(
            "journal", row["id"], row["occurred_at"], row["operation_type"],
            "Driver prende in carico" if row["operation_type"] == "check_out" else "Driver riconsegna il mezzo",
            "journal",
        ))
    for row in damages:
        events.append(_event("damage", row["id"], row["occurred_at"], "damage",
                             f"Danno {row['case_number']}", "damage"))
        events.append(_event("damage", row["id"], row.get("closed_at"), "damage_closed",
                             f"Pratica {row['case_number']} chiusa", "damage"))
    for row in maintenances:
        events.append(_event("maintenance", row["id"], row["opened_at"], "maintenance_opened",
                             f"Manutenzione {row['maintenance_number']} aperta", "maintenance"))
        events.append(_event("maintenance", row["id"], row.get("completed_at"), "maintenance_completed",
                             f"Manutenzione {row['maintenance_number']} completata", "maintenance"))
    for row in rentals:
        events.append(_event("rental", row["id"], row["start_date"], "rental_started",
                             f"Noleggio {row['replacement_vehicle']} avviato", "rentals"))
        events.append(_event("rental", row["id"], row.get("end_date"), "rental_ended",
                             f"Noleggio {row['replacement_vehicle']} concluso", "rentals"))
    for row in documents:
        events.append(_event("document", row["id"], row["created_at"], "document_registered",
                             f"Documento {row['title']} registrato", "documents"))
    for row in franchises:
        events.append(_event("franchise", row["id"], row["created_at"], "franchise_opened",
                             "Valutazione franchigia aperta", "franchises"))
    if status_event:
        current = status_event["details"].get("current") or status_event["details"].get("status")
        events.append(_event("operational_status", asset_id, status_event["occurred_at"],
                             "status_changed", f"Stato operativo: {current or 'aggiornato'}", "library"))
    unique = {item["id"]: item for item in events if item}
    return sorted(unique.values(), key=lambda item: item["occurred_at"], reverse=True)


def fleet_vision(vehicle_id: int | None = None) -> dict:
    data = repository.snapshot()
    deadlines = _group(list_deadlines()["items"])
    damages, maintenances = _group(data["damages"]), _group(data["maintenances"])
    documents, franchises = _group(data["documents"]), _group(data["franchises"])
    rentals = _group(data["rentals"])
    movements = _group([
        {**row, "vehicle_id": row["asset_id"]} for row in data["movements"]
    ])
    insurance = {int(row["vehicle_id"]): row for row in data["insurance"]}
    events = {int(row["asset_id"]): row for row in data["events"]}
    today = date.today()
    items = []
    for asset in data["assets"]:
        asset_id = int(asset["id"])
        if vehicle_id and asset_id != vehicle_id:
            continue
        status = asset["availability"]
        event = events.get(asset_id)
        stopped_days = 0 if status in OPERATIVE else None
        if status not in OPERATIVE and event:
            occurred = datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00")).date()
            stopped_days = max(0, (today - occurred).days)
        asset_damages = damages[asset_id]
        asset_maintenance = maintenances[asset_id]
        asset_franchises = franchises[asset_id]
        asset_rentals = rentals[asset_id]
        imminent = [item for item in deadlines[asset_id] if 0 <= item["days_remaining"] <= 30]
        policy = insurance.get(asset_id)
        asset_movements = movements[asset_id]
        timeline = _timeline(
            asset_id, asset_movements, asset_damages, asset_maintenance,
            asset_rentals, documents[asset_id], asset_franchises, event,
        )
        last_movement = max(asset_movements, key=lambda row: row["occurred_at"], default=None)
        last_damage = max(asset_damages, key=lambda row: row["occurred_at"], default=None)
        last_maintenance = max(
            asset_maintenance,
            key=lambda row: row.get("completed_at") or row["opened_at"],
            default=None,
        )
        contract_expiring = sum(
            item["source_module"] == "contract" for item in imminent
        )
        insurance_expired = int(bool(policy and policy["status"] == "scaduta"))
        insights = [
            {
                "key": "last_use", "label": "Ultimo utilizzo",
                "value": last_movement["occurred_at"] if last_movement else None,
                "source": "Driver Journal", "module": "journal",
                "source_id": last_movement["id"] if last_movement else None,
            },
            {
                "key": "last_damage", "label": "Ultimo danno",
                "value": last_damage["case_number"] if last_damage else None,
                "source": "Danni", "module": "damage",
                "source_id": last_damage["id"] if last_damage else None,
            },
            {
                "key": "last_maintenance", "label": "Ultima manutenzione",
                "value": last_maintenance["maintenance_number"] if last_maintenance else None,
                "source": "Manutenzioni", "module": "maintenance",
                "source_id": last_maintenance["id"] if last_maintenance else None,
            },
            {
                "key": "last_status_change", "label": "Ultimo cambio stato",
                "value": event["occurred_at"] if event else None,
                "source": "Stato operativo", "module": "library", "source_id": asset_id,
            },
            {
                "key": "missing_documents", "label": "Documenti mancanti",
                "value": sum(row["status"] == "mancante" for row in documents[asset_id]),
                "source": "Documenti", "module": "documents", "source_id": None,
            },
            {
                "key": "imminent_deadlines", "label": "Scadenze imminenti",
                "value": len(imminent), "source": "Scadenziario",
                "module": "deadlines", "source_id": None,
            },
            {
                "key": "insurance", "label": "Assicurazione",
                "value": policy["policy_number"] if policy else None,
                "source": "Assicurazioni", "module": "insurance",
                "source_id": policy["id"] if policy else None,
            },
            {
                "key": "contract", "label": "Contratto",
                "value": asset.get("contract_number"), "source": "Fleet Asset Profile",
                "module": "library", "source_id": asset_id,
            },
            {
                "key": "active_rental", "label": "Noleggio attivo",
                "value": next((row["replacement_vehicle"] for row in asset_rentals if row["status"] in ACTIVE_RENTAL), None),
                "source": "Noleggi", "module": "rentals", "source_id": None,
            },
            {
                "key": "open_franchise", "label": "Franchigia aperta",
                "value": sum(row["status"] in OPEN_FRANCHISE for row in asset_franchises),
                "source": "Franchigie", "module": "franchises", "source_id": None,
            },
        ]
        items.append({
            **asset,
            "operational_status": status,
            "operational_status_reason": (event or {}).get("details", {}).get("reason"),
            "movement_count": len(asset_movements),
            "damage_open": sum(row["status"] in OPEN_DAMAGE for row in asset_damages),
            "damage_closed": sum(row["status"] in {"chiusa", "annullata"} for row in asset_damages),
            "maintenance_open": sum(row["status"] in OPEN_MAINTENANCE for row in asset_maintenance),
            "maintenance_completed": sum(row["status"] == "completata" for row in asset_maintenance),
            "missing_documents": sum(row["status"] == "mancante" for row in documents[asset_id]),
            "insurance": policy,
            "franchises_open": sum(row["status"] in OPEN_FRANCHISE for row in asset_franchises),
            "rentals_active": sum(row["status"] in ACTIVE_RENTAL for row in asset_rentals),
            "deadlines_imminent": len(imminent),
            "deadlines": imminent,
            "days_stopped": stopped_days,
            "damage_count": len(asset_damages),
            "maintenance_count": len(asset_maintenance),
            "rental_count": len(asset_rentals),
            "insurance_expired": insurance_expired,
            "contracts_expiring": contract_expiring,
            "timeline": timeline,
            "insights": insights,
            "latest": {
                "use": last_movement,
                "damage": last_damage,
                "maintenance": last_maintenance,
                "status_change": event,
            },
        })
    return {
        "items": items,
        "total": len(items),
        "summary": {
            "operational": sum(item["operational_status"] in OPERATIVE for item in items),
            "unavailable": sum(item["operational_status"] in UNAVAILABLE for item in items),
            "in_maintenance": sum(item["operational_status"] in MAINTENANCE for item in items),
            "open_damages": sum(item["damage_open"] for item in items),
            "open_maintenances": sum(item["maintenance_open"] for item in items),
            "active_rentals": sum(item["rentals_active"] for item in items),
            "missing_documents": sum(item["missing_documents"] for item in items),
            "expired_insurance": sum(item["insurance_expired"] for item in items),
            "expiring_contracts": sum(item["contracts_expiring"] for item in items),
        },
    }
