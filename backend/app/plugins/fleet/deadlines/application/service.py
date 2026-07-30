from datetime import date

from app.plugins.fleet.deadlines.infrastructure import repository


MODULE_LABELS = {
    "document": "Documenti",
    "insurance": "Assicurazioni",
    "contract": "Contratti",
    "maintenance": "Manutenzioni",
}


def _presentation(item: dict, today: date) -> dict:
    due = date.fromisoformat(str(item["due_date"])[:10])
    days = (due - today).days
    if days < 0:
        status, bucket = "Scaduta", "expired"
    elif days == 0:
        status, bucket = "Oggi", "today"
    elif days <= 7:
        status, bucket = "Prossimi 7 giorni", "seven_days"
    elif days <= 30:
        status, bucket = "Prossimi 30 giorni", "thirty_days"
    else:
        status, bucket = "Valida", "valid"
    return {
        **item,
        "id": f'{item["source_module"]}:{item["source_id"]}',
        "module_label": MODULE_LABELS[item["source_module"]],
        "status": status,
        "status_bucket": bucket,
        "days_remaining": days,
    }


def list_deadlines(vehicle_id: int | None = None) -> dict:
    today = date.today()
    items = [_presentation(item, today) for item in repository.list_sources(vehicle_id)]
    items.sort(key=lambda item: (item["due_date"], item["source_module"], item["source_id"]))
    return {
        "items": items,
        "summary": {
            "expired": sum(item["status_bucket"] == "expired" for item in items),
            "expiring": sum(0 <= item["days_remaining"] <= 30 for item in items),
            "today": sum(item["status_bucket"] == "today" for item in items),
            "next_30_days": sum(0 <= item["days_remaining"] <= 30 for item in items),
        },
        "total": len(items),
        "generated_on": today.isoformat(),
    }
