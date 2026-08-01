import json
from datetime import date, datetime, timedelta, timezone

from app.auth import repository as auth_repository
from app.plugins.fleet.journal.domain.operational_day import operational_date
from app.plugins.fleet.journal.control_room import repository


def _iso_date(value: str) -> date:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def _present(item: dict, can_delete_media: bool = False) -> dict:
    incomplete = bool(item.get("incomplete"))
    anomaly = bool(item.get("anomaly_present"))
    lifecycle = item.get("lifecycle_status")
    status = (
        lifecycle
        if incomplete and lifecycle in {"generated", "opened", "in_progress"}
        else "con_anomalia" if anomaly else "completed"
    )
    occurred_at = item.get("occurred_at") or item["created_at"]
    movement_id = None if incomplete else item["id"]
    return {
        **item,
        "occurred_at": occurred_at,
        "anomaly_present": anomaly,
        "status": status,
        "warnings": json.loads(str(item.get("warnings_json") or "[]")),
        "origin": {
            "shared_link": "Shared link",
            "fleet_manager": "Sessione preconfigurata",
            "driver": "Movimentazione storica",
        }.get(str(item.get("source") or "driver"), "Movimentazione storica"),
        "photo_count": sum(not media["media_type"].startswith("video") for media in item["media"]),
        "video_count": sum(media["media_type"].startswith("video") for media in item["media"]),
        "operational_document_id": (
            f"JM-{movement_id.split('-')[0].upper()}" if movement_id else None
        ),
        "receipt_url": (
            f"/api/plugins/fleet/v1/journal/movements/{movement_id}/receipt"
            if movement_id else None
        ),
        "permissions": {"delete_media": can_delete_media},
    }


def _matches(item: dict, filters: dict, today: date) -> bool:
    occurred = date.fromisoformat(str(item.get("operational_date") or _iso_date(item["occurred_at"])))
    search = str(filters.get("search") or "").casefold().strip()
    if search:
        haystack = " ".join(str(item.get(key) or "") for key in (
            "id", "declared_driver_identifier", "plate_snapshot", "occurred_at",
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
    status = filters.get("status")
    if status and item.get("status") != status:
        return False
    media = filters.get("media")
    has_media = bool(item.get("media"))
    if media == "with" and not has_media:
        return False
    if media == "without" and has_media:
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
    if vehicle_id and int(item["asset_id"]) != int(vehicle_id):
        return False
    selected_date = filters.get("date")
    return not selected_date or occurred == date.fromisoformat(str(selected_date))


def list_procedures(
    filters: dict,
    organization_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    can_delete_media: bool = False,
) -> dict:
    organization = auth_repository.organization_by_id(organization_id)
    timezone_name = organization["timezone"] if organization else "Europe/Rome"
    start = organization["operational_day_start_hour"] if organization else 4
    today = operational_date(datetime.now(timezone.utc), timezone_name, start)
    items = [_present(item, can_delete_media) for item in repository.list_procedures(organization_id, start_date, end_date)]
    items = [item for item in items if _matches(item, filters, today)]
    return {
        "items": items,
        "total": len(items),
        "summary": {
            "completed_today": sum(
                item["status"] in {"completed", "con_anomalia"}
                and date.fromisoformat(str(item.get("operational_date") or _iso_date(item["occurred_at"]))) == today
                for item in items
            ),
            "check_outs": sum(item["operation_type"] == "check_out" for item in items),
            "check_ins": sum(item["operation_type"] == "check_in" for item in items),
            "with_anomalies": sum(item["anomaly_present"] for item in items),
            "incomplete": sum(
                item["status"] in {"generated", "opened", "in_progress"}
                for item in items
            ),
        },
    }


def get_procedure(procedure_id: str, organization_id: str, can_delete_media: bool = False) -> dict | None:
    item = repository.get_procedure(procedure_id, organization_id)
    return _present(item, can_delete_media) if item else None
