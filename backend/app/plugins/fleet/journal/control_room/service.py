from datetime import date, datetime, timedelta

from app.plugins.fleet.journal.control_room import repository


def _iso_date(value: str) -> date:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def _present(item: dict) -> dict:
    incomplete = bool(item.get("incomplete"))
    anomaly = bool(item.get("anomaly_present"))
    status = "incompleta" if incomplete else "con_anomalia" if anomaly else "completata"
    occurred_at = item.get("occurred_at") or item["created_at"]
    movement_id = None if incomplete else item["id"]
    return {
        **item,
        "occurred_at": occurred_at,
        "anomaly_present": anomaly,
        "status": status,
        "photo_count": sum(not media["media_type"].startswith("video") for media in item["media"]),
        "video_count": sum(media["media_type"].startswith("video") for media in item["media"]),
        "operational_document_id": (
            f"JM-{movement_id.split('-')[0].upper()}" if movement_id else None
        ),
        "receipt_url": (
            f"/api/plugins/fleet/v1/journal/movements/{movement_id}/receipt"
            if movement_id else None
        ),
    }


def _matches(item: dict, filters: dict) -> bool:
    today = date.today()
    occurred = _iso_date(item["occurred_at"])
    search = str(filters.get("search") or "").casefold().strip()
    if search:
        haystack = " ".join(str(item.get(key) or "") for key in (
            "declared_driver_identifier", "plate_snapshot", "occurred_at",
            "anomaly_description", "operational_note",
        )).casefold()
        if search not in haystack:
            return False
    operation = filters.get("operation_type")
    if operation and item.get("operation_type") != operation:
        return False
    anomaly = filters.get("anomaly")
    if anomaly == "with" and not item["anomaly_present"]:
        return False
    if anomaly == "without" and item["anomaly_present"]:
        return False
    period = filters.get("period")
    if period == "today" and occurred != today:
        return False
    if period == "7d" and occurred < today - timedelta(days=6):
        return False
    if period == "30d" and occurred < today - timedelta(days=29):
        return False
    vehicle_id = filters.get("vehicle_id")
    return not vehicle_id or int(item["asset_id"]) == int(vehicle_id)


def list_procedures(filters: dict) -> dict:
    items = [_present(item) for item in repository.list_procedures()]
    items = [item for item in items if _matches(item, filters)]
    today = date.today()
    return {
        "items": items,
        "total": len(items),
        "summary": {
            "completed_today": sum(
                item["status"] != "incompleta" and _iso_date(item["occurred_at"]) == today
                for item in items
            ),
            "check_outs": sum(item["operation_type"] == "check_out" for item in items),
            "check_ins": sum(item["operation_type"] == "check_in" for item in items),
            "with_anomalies": sum(item["anomaly_present"] for item in items),
            "incomplete": sum(item["status"] == "incompleta" for item in items),
        },
    }


def get_procedure(procedure_id: str) -> dict | None:
    item = repository.get_procedure(procedure_id)
    return _present(item) if item else None
