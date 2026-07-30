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


def fleet_vision(vehicle_id: int | None = None) -> dict:
    data = repository.snapshot()
    deadlines = _group(list_deadlines()["items"])
    damages, maintenances = _group(data["damages"]), _group(data["maintenances"])
    documents, franchises = _group(data["documents"]), _group(data["franchises"])
    rentals = _group(data["rentals"])
    movements: dict[int, int] = defaultdict(int)
    for row in data["movements"]:
        movements[int(row["asset_id"])] += 1
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
        items.append({
            **asset,
            "operational_status": status,
            "operational_status_reason": (event or {}).get("details", {}).get("reason"),
            "movement_count": movements[asset_id],
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
        },
    }
