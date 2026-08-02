import calendar
from datetime import date, datetime

from app.plugins.fleet.journal.control_room import service as control_room
from app.plugins.fleet.journal.control_room import repository


def month_snapshot(month: str | None, organization_id: str) -> dict:
    context = control_room.operational_context(organization_id)
    month = month or context["operational_date"][:7]
    year, month_number = (int(value) for value in month.split("-"))
    last_day = calendar.monthrange(year, month_number)[1]
    start = date(year, month_number, 1)
    end = date(year, month_number, last_day)
    days = repository.month_counts(
        organization_id, start.isoformat(), end.isoformat()
    )
    return {
        "month": month,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": days,
        "total": sum(int(item["total"]) for item in days),
        "context": context,
    }


def day_snapshot(day: str, organization_id: str, filters: dict, can_delete_media: bool = False) -> dict:
    date.fromisoformat(day)
    unfiltered = control_room.list_procedures(
        {"date": day}, organization_id, day, day, can_delete_media
    )
    active_filters = {key: value for key, value in filters.items() if value not in {None, ""}}
    result = unfiltered if not active_filters else control_room.list_procedures(
        {**active_filters, "date": day}, organization_id, day, day, can_delete_media
    )
    items = result["items"]
    summary_items = unfiltered["items"]
    operation_rank = {"check_out": 0, "check_in": 1}
    items.sort(key=lambda item: (
        datetime.fromisoformat(str(item["occurred_at"]).replace("Z", "+00:00")).timestamp(),
        operation_rank.get(str(item.get("operation_type")), 2),
        str(item["id"]),
    ))
    return {**result, "date": day, "summary": {
        "total": len(summary_items),
        "check_outs": sum(item["operation_type"] == "check_out" for item in summary_items),
        "check_ins": sum(item["operation_type"] == "check_in" for item in summary_items),
        "complete": sum(item["status"] in {"completed", "con_anomalia"} for item in summary_items),
        "incomplete": sum(item["status"] in {"generated", "opened", "in_progress"} for item in summary_items),
        "with_anomalies": sum(bool(item["anomaly_present"]) for item in summary_items),
        "with_media": sum(bool(item["media"]) for item in summary_items),
    }}
