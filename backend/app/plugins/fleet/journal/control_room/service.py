import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.auth import repository as auth_repository
from app.plugins.fleet.journal.domain.operational_day import operational_date
from app.plugins.fleet.journal.control_room import repository
from app.plugins.fleet.journal.control_room.completion_presenter import apply_filter as apply_completion_filter
from app.plugins.fleet.journal.control_room.completion_service import journal_completion


def _iso_date(value: str) -> date:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def operational_context(organization_id: str) -> dict:
    organization = auth_repository.organization_by_id(organization_id)
    timezone_name = organization["timezone"] if organization else "Europe/Rome"
    start = organization["operational_day_start_hour"] if organization else 4
    current = operational_date(datetime.now(timezone.utc), timezone_name, start)
    for session in repository.sessions_without_operational_date(organization_id):
        reference = datetime.fromisoformat(str(session["reference_at"]).replace("Z", "+00:00"))
        repository.set_operational_date(
            str(session["id"]), operational_date(reference, timezone_name, start).isoformat()
        )
    return {
        "operational_date": current.isoformat(),
        "timezone": timezone_name,
        "operational_day_start_hour": int(start),
    }


def _is_late(item: dict, timezone_name: str) -> bool:
    if item.get("lifecycle_status") not in {"generated", "opened", "in_progress"}:
        return False
    scheduled_at = item.get("scheduled_at")
    if not scheduled_at:
        return False
    scheduled = datetime.fromisoformat(str(scheduled_at).replace("Z", "+00:00"))
    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=ZoneInfo(timezone_name))
    return scheduled < datetime.now(ZoneInfo(timezone_name))


def _present(
    item: dict, can_delete_media: bool = False, timezone_name: str = "Europe/Rome"
) -> dict:
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
        "is_late": _is_late(item, timezone_name) if incomplete else False,
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
    plate = str(filters.get("plate") or "").casefold().strip()
    if plate and plate not in str(item.get("plate_snapshot") or "").casefold():
        return False
    driver = str(filters.get("driver") or "").casefold().strip()
    if driver and driver not in str(item.get("declared_driver_identifier") or "").casefold():
        return False
    operation = filters.get("operation_type")
    if operation and item.get("operation_type") != operation:
        return False
    anomaly = filters.get("anomaly")
    if anomaly == "with" and not item["anomaly_present"]:
        return False
    status = filters.get("status")
    if status == "complete" and item.get("status") not in {"completed", "con_anomalia"}:
        return False
    if status == "incomplete" and item.get("status") not in {"generated", "opened", "in_progress"}:
        return False
    if status and status not in {"complete", "incomplete"} and item.get("status") != status:
        return False
    media = filters.get("media")
    has_media = bool(item.get("media"))
    if media == "with" and not has_media:
        return False
    if media == "without" and has_media:
        return False
    if anomaly == "without" and item["anomaly_present"]:
        return False
    live_status = filters.get("live_status")
    if live_status == "not_started" and item.get("status") != "generated":
        return False
    if live_status == "in_progress" and item.get("status") not in {"opened", "in_progress"}:
        return False
    if live_status == "completed" and item.get("status") not in {"completed", "con_anomalia"}:
        return False
    if live_status == "anomaly" and not item.get("anomaly_present"):
        return False
    if live_status == "late" and not item.get("is_late"):
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
    current_scope: bool = False,
) -> dict:
    context = operational_context(organization_id)
    today = date.fromisoformat(context["operational_date"])
    query_start, query_end = start_date, end_date
    if current_scope:
        query_start, query_end = (today - timedelta(days=1)).isoformat(), today.isoformat()
    items = [_present(item, can_delete_media, context["timezone"]) for item in repository.list_procedures(
        organization_id, query_start, query_end
    )]
    if current_scope:
        previous = today - timedelta(days=1)
        items = [item for item in items if (
            date.fromisoformat(str(item.get("operational_date") or _iso_date(item["occurred_at"]))) == today
            or (
                date.fromisoformat(str(item.get("operational_date") or _iso_date(item["occurred_at"]))) == previous
                and item["status"] in {"generated", "opened", "in_progress"}
            )
        )]
    current_items = [item for item in items if
                     date.fromisoformat(str(item.get("operational_date") or _iso_date(item["occurred_at"]))) == today]
    completion = journal_completion(context, current_items)
    items = [item for item in items if _matches(item, filters, today)]
    items, completion = apply_completion_filter(
        items, completion, filters.get("completion_filter")
    )
    return {
        "items": items,
        "total": len(items),
        "context": context,
        "completion": completion,
        "summary": {
            "expected_drivers": completion["drivers_expected"],
            "not_started": sum(item["status"] == "generated" for item in current_items),
            "in_progress_live": sum(
                item["status"] in {"opened", "in_progress"} for item in current_items
            ),
            "completed_live": sum(
                item["status"] in {"completed", "con_anomalia"} for item in current_items
            ),
            "late": sum(item["is_late"] for item in current_items),
            "completed_today": sum(
                item["status"] in {"completed", "con_anomalia"}
                for item in current_items
            ),
            "check_outs": sum(item["operation_type"] == "check_out" for item in current_items),
            "check_ins": sum(item["operation_type"] == "check_in" for item in current_items),
            "with_anomalies": sum(item["anomaly_present"] for item in current_items),
            "incomplete": sum(
                item["status"] in {"generated", "opened", "in_progress"}
                for item in current_items
            ),
        },
    }


def get_procedure(procedure_id: str, organization_id: str, can_delete_media: bool = False) -> dict | None:
    item = repository.get_procedure(procedure_id, organization_id)
    context = operational_context(organization_id)
    return _present(item, can_delete_media, context["timezone"]) if item else None
