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


def _decision(
    rule: str,
    asset_id: int,
    title: str,
    description: str,
    priority: str,
    origin: str,
    module: str,
    evidence: dict,
) -> dict:
    return {
        "id": f"{rule}:{asset_id}",
        "rule": rule,
        "title": title,
        "description": description,
        "priority": priority,
        "origin": origin,
        "module": module,
        "evidence": evidence,
        "why": " · ".join(
            f"{key}: {value}" for key, value in evidence.items() if value is not None
        ),
    }


def _decisions(
    asset: dict,
    damages: list[dict],
    maintenances: list[dict],
    documents: list[dict],
    policy: dict | None,
    franchises: list[dict],
    rentals: list[dict],
    imminent_deadlines: list[dict],
) -> list[dict]:
    asset_id = int(asset["id"])
    plate = asset["plate"] or asset["external_identifier"]
    result = []
    contract = next(
        (item for item in imminent_deadlines if item["source_module"] == "contract"),
        None,
    )
    if contract:
        result.append(_decision(
            "contract_expiring", asset_id, "Contratto in scadenza",
            f"Il contratto del mezzo {plate} scade entro 30 giorni.", "media",
            "Fleet Asset Profile", "library",
            {
                "tipo contratto": asset.get("contract_type"),
                "scadenza": contract["due_date"],
                "giorni": contract["days_remaining"],
            },
        ))
    if policy and policy["status"] == "scaduta":
        result.append(_decision(
            "insurance_expired", asset_id, "Assicurazione scaduta",
            f"La polizza associata al mezzo {plate} risulta scaduta.", "alta",
            "Assicurazioni", "insurance",
            {"polizza": policy["policy_number"], "scadenza": policy["expires_on"]},
        ))
    missing = sum(row["status"] == "mancante" for row in documents)
    if missing:
        result.append(_decision(
            "documents_missing", asset_id, "Documentazione incompleta",
            f"Il mezzo {plate} presenta documenti con stato mancante.", "media",
            "Documenti", "documents", {"documenti mancanti": missing},
        ))
    if asset["availability"] in UNAVAILABLE | MAINTENANCE:
        result.append(_decision(
            "vehicle_not_operational", asset_id, "Mezzo non operativo",
            f"Lo stato operativo corrente del mezzo {plate} non è disponibile.", "alta",
            "Stato operativo", "library", {"stato": asset["availability"]},
        ))
    open_damages = [row for row in damages if row["status"] in OPEN_DAMAGE]
    if open_damages:
        result.append(_decision(
            "damage_open", asset_id, "Pratica danno aperta",
            f"Il mezzo {plate} presenta almeno una pratica Danni aperta.", "alta",
            "Danni", "damage",
            {"pratiche aperte": len(open_damages), "ultima pratica": open_damages[-1]["case_number"]},
        ))
    open_maintenance = [row for row in maintenances if row["status"] in OPEN_MAINTENANCE]
    if open_maintenance:
        result.append(_decision(
            "maintenance_open", asset_id, "Intervento manutenzione in corso",
            f"Il mezzo {plate} presenta una manutenzione non conclusa.", "media",
            "Manutenzioni", "maintenance",
            {"interventi aperti": len(open_maintenance), "stato": open_maintenance[-1]["status"]},
        ))
    open_franchises = [row for row in franchises if row["status"] in OPEN_FRANCHISE]
    if open_franchises:
        result.append(_decision(
            "franchise_open", asset_id, "Franchigia da verificare",
            f"Il mezzo {plate} presenta una franchigia ancora aperta.", "media",
            "Franchigie", "franchises", {"franchigie aperte": len(open_franchises)},
        ))
    active_rentals = [row for row in rentals if row["status"] in ACTIVE_RENTAL]
    if active_rentals:
        result.append(_decision(
            "rental_active", asset_id, "Mezzo sostitutivo attivo",
            f"Per il mezzo {plate} risulta attivo un veicolo sostitutivo.", "bassa",
            "Noleggi", "rentals",
            {"mezzo sostitutivo": active_rentals[-1]["replacement_vehicle"], "stato": active_rentals[-1]["status"]},
        ))
    other_deadlines = [
        item for item in imminent_deadlines if item["source_module"] != "contract"
    ]
    if other_deadlines:
        nearest = min(other_deadlines, key=lambda item: item["days_remaining"])
        result.append(_decision(
            "deadline_soon", asset_id, "Scadenza entro 30 giorni",
            f"Il mezzo {plate} presenta una scadenza operativa imminente.", "bassa",
            "Scadenziario", "deadlines",
            {
                "tipo": nearest["deadline_type"],
                "scadenza": nearest["due_date"],
                "giorni": nearest["days_remaining"],
            },
        ))
    order = {"alta": 0, "media": 1, "bassa": 2}
    return sorted(result, key=lambda item: (order[item["priority"]], item["rule"]))


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
        decisions = _decisions(
            asset, asset_damages, asset_maintenance, documents[asset_id],
            policy, asset_franchises, asset_rentals, imminent,
        )
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
            "decisions": decisions,
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
            "decisions": sum(len(item["decisions"]) for item in items),
            "high_priority_decisions": sum(
                decision["priority"] == "alta"
                for item in items
                for decision in item["decisions"]
            ),
        },
    }
