import calendar
from collections import defaultdict
from datetime import date

from app.plugins.fleet.journal.control_room import service as control_room


def month_snapshot(month: str, organization_id: str) -> dict:
    year, month_number = (int(value) for value in month.split("-"))
    last_day = calendar.monthrange(year, month_number)[1]
    start = date(year, month_number, 1)
    end = date(year, month_number, last_day)
    result = control_room.list_procedures({}, organization_id, start.isoformat(), end.isoformat())
    grouped: dict[str, dict] = defaultdict(lambda: {"total": 0, "anomalies": 0, "incomplete": 0, "with_media": 0})
    for item in result["items"]:
        day = str(item.get("operational_date") or item["occurred_at"][:10])
        grouped[day]["total"] += 1
        grouped[day]["anomalies"] += int(bool(item["anomaly_present"]))
        grouped[day]["incomplete"] += int(item["status"] in {"generated", "opened", "in_progress"})
        grouped[day]["with_media"] += int(bool(item["media"]))
    return {"month": month, "start": start.isoformat(), "end": end.isoformat(),
            "days": [{"date": day, **counts} for day, counts in sorted(grouped.items())],
            "total": len(result["items"])}


def day_snapshot(day: str, organization_id: str, filters: dict, can_delete_media: bool = False) -> dict:
    date.fromisoformat(day)
    result = control_room.list_procedures({**filters, "date": day}, organization_id, day, day, can_delete_media)
    items = result["items"]
    return {**result, "date": day, "summary": {
        "total": len(items),
        "check_outs": sum(item["operation_type"] == "check_out" for item in items),
        "check_ins": sum(item["operation_type"] == "check_in" for item in items),
        "complete": sum(item["status"] in {"completed", "con_anomalia"} for item in items),
        "incomplete": sum(item["status"] in {"generated", "opened", "in_progress"} for item in items),
        "with_anomalies": sum(bool(item["anomaly_present"]) for item in items),
        "with_media": sum(bool(item["media"]) for item in items),
    }}
