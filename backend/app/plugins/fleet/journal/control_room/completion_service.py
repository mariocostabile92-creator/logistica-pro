import re
from datetime import datetime, timedelta, timezone

from app.plugins.fleet.journal.control_room import completion_repository
from app.plugins.fleet.journal.control_room.planning_vehicle_adapter import (
    assignment_is_active,
    fleet_asset_for_assignment,
    index_fleet_assets_by_plate,
)
from app.plugins.fleet.journal.domain.operational_day import operational_bounds, organization_timezone


COMPLETED = {"completed", "con_anomalia"}
EXCEPTION_EVENT_TYPES = {
    "route_aborted", "route_cancelled", "driver_absent", "driver_removed",
    "procedure_cancelled",
}
TIME_PATTERN = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)")


def _identity(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def _assignment_exception(assignment: dict, events: list[dict]) -> str | None:
    if not assignment_is_active(assignment):
        return f"assignment_{assignment['assignment_status']}"
    if not assignment.get("driver_id") and not assignment.get("driver_name"):
        return "driver_removed"
    route = _identity(assignment.get("route_id"))
    driver = _identity(assignment.get("driver_id") or assignment.get("driver_name"))
    for event in events:
        event_type = str(event.get("event_type") or "")
        entity = _identity(event.get("entity_id"))
        if event_type not in EXCEPTION_EVENT_TYPES:
            continue
        if event_type.startswith("route_") and entity == route:
            return event_type
        if event_type.startswith("driver_") and entity == driver:
            return event_type
    signals = " ".join([
        *map(str, assignment.get("warnings") or []),
        *map(str, assignment.get("reasons") or []),
        str(assignment.get("notes") or ""),
    ]).casefold()
    if any(word in signals for word in ("annullat", "cancelled", "rimosso", "removed")):
        return "assignment_cancelled"
    return None


def _scheduled_at(assignment: dict, operation_type: str, begins: datetime, ends: datetime) -> datetime:
    match = TIME_PATTERN.search(str(assignment.get("cycle_or_wave") or ""))
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        local = begins.astimezone(begins.tzinfo).replace(hour=hour, minute=minute, second=0, microsecond=0)
        if local < begins:
            local += timedelta(days=1)
        checkout = local
    else:
        checkout = begins + timedelta(hours=2)
    if operation_type == "check_out":
        return checkout
    return min(checkout + timedelta(hours=10), ends - timedelta(hours=2))


def _status(now: datetime, scheduled: datetime, critical: datetime) -> tuple[str, int]:
    if now < scheduled:
        return "atteso", 0
    delay = max(0, int((now - scheduled).total_seconds() // 60))
    return ("critico" if now >= critical else "in_ritardo"), delay


def _matched_procedure(expectation: dict, procedures: list[dict]) -> dict | None:
    aliases = {_identity(expectation["driver_id"]), _identity(expectation["driver_name"])} - {""}
    candidates = [item for item in procedures if (
        item.get("operation_type") == expectation["operation_type"]
        and _identity(item.get("declared_driver_identifier")) in aliases
    )]
    if not candidates:
        return None
    return max(candidates, key=lambda item: str(item.get("occurred_at") or item.get("created_at") or ""))


def _decision_cards(missing: list[dict], planning_id: int) -> list[dict]:
    decisions: list[dict] = []
    for operation, title in (("check_in", "rientri"), ("check_out", "prese in carico")):
        affected = [item for item in missing if item["operation_type"] == operation]
        if affected:
            decisions.append({
                "id": f"journal_missing_{operation}:{planning_id}",
                "rule": f"journal_missing_{operation}",
                "title": f"Mancano {len(affected)} {title}",
                "description": f"Il planning richiede ancora {len(affected)} procedure Journal da completare.",
                "priority": "alta" if operation == "check_in" else "media",
                "origin": "Journal Completion",
                "module": "journal",
                "vehicle_id": None,
                "vehicle": "Intera flotta",
                "evidence": {"planning": planning_id, "procedure mancanti": len(affected)},
                "why": f"Planning {planning_id} · {len(affected)} procedure non completate",
                "actions": [{"module": "journal", "label": "Apri Journal"}],
            })
    for item in missing:
        if item["status"] not in {"in_ritardo", "critico"}:
            continue
        decisions.append({
            "id": f"journal_missing_driver:{planning_id}:{item['driver_key']}:{item['operation_type']}",
            "rule": "journal_driver_incomplete",
            "title": f"{item['driver_name']} non ha completato il GDB",
            "description": f"{item['procedure_label']} non completata; ritardo {item['delay_label']}.",
            "priority": "alta" if item["status"] == "critico" or item["operation_type"] == "check_in" else "media",
            "origin": "Journal Completion",
            "module": "journal",
            "vehicle_id": item.get("vehicle_id"),
            "vehicle": item.get("plate") or "Mezzo non associato",
            "driver_id": item.get("driver_id"),
            "evidence": {
                "planning": planning_id,
                "driver": item["driver_name"],
                "procedura": item["procedure_label"],
                "ritardo": item["delay_label"],
            },
            "why": f"Planning {planning_id} · {item['procedure_label']} attesa alle {item['expected_time']}",
            "actions": [
                {"module": "workforce", "label": "Apri Driver"},
                {"module": "journal", "label": "Apri Journal"},
            ],
        })
    return decisions


def journal_completion(context: dict, procedures: list[dict], now: datetime | None = None) -> dict:
    snapshot = completion_repository.planning_snapshot(context["operational_date"])
    empty = {
        "planning_id": None, "operational_date": context["operational_date"],
        "drivers_expected": 0,
        "check_out": {"expected": 0, "completed": 0, "missing": 0},
        "check_in": {"expected": 0, "completed": 0, "missing": 0},
        "procedures": {"open": 0, "in_progress": 0, "late": 0, "anomalies": 0},
        "missing": [], "exceptions": [], "decisions": [], "active_filter": "all",
    }
    if not snapshot:
        return empty
    begins_utc, ends_utc = operational_bounds(
        datetime.fromisoformat(context["operational_date"]).date(),
        context["timezone"], context["operational_day_start_hour"],
    )
    zone = organization_timezone(context["timezone"])
    begins, ends = begins_utc.astimezone(zone), ends_utc.astimezone(zone)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(zone)
    assets = index_fleet_assets_by_plate(snapshot["assets"])
    drivers: dict[str, dict] = {}
    exceptions = []
    for assignment in snapshot["assignments"]:
        reason = _assignment_exception(assignment, snapshot["events"])
        driver_key = _identity(assignment.get("driver_id") or assignment.get("driver_name"))
        if reason:
            exceptions.append({
                "assignment_id": assignment["id"], "route_id": assignment["route_id"],
                "driver": assignment.get("driver_name") or assignment.get("driver_id"),
                "reason": reason,
            })
            continue
        if not driver_key or driver_key in drivers:
            continue
        asset = fleet_asset_for_assignment(assignment, assets)
        drivers[driver_key] = {
            "driver_key": driver_key,
            "driver_id": assignment.get("driver_id"),
            "driver_name": assignment.get("driver_name") or assignment.get("driver_id"),
            "route_id": assignment.get("route_id"),
            "planning_id": snapshot["planning"]["id"],
            "plate": assignment.get("plate"),
            "vehicle_id": asset.get("id") if asset else None,
            "vehicle_model": asset.get("category") if asset else None,
            "assignment": assignment,
        }
    expectations = []
    for driver in drivers.values():
        for operation_type in ("check_out", "check_in"):
            scheduled = _scheduled_at(driver["assignment"], operation_type, begins, ends)
            critical = begins + timedelta(hours=8) if operation_type == "check_out" else ends
            expectation = {**driver, "operation_type": operation_type}
            procedure = _matched_procedure(expectation, procedures)
            completed = bool(procedure and procedure.get("status") in COMPLETED)
            state, delay = ("completato", 0) if completed else _status(current, scheduled, critical)
            public_expectation = {
                key: value for key, value in expectation.items() if key != "assignment"
            }
            expectations.append({
                **public_expectation,
                "procedure_label": "Presa in carico" if operation_type == "check_out" else "Rientro",
                "expected_at": scheduled.isoformat(),
                "expected_time": scheduled.astimezone(begins.tzinfo).strftime("%H:%M"),
                "status": state,
                "delay_minutes": delay,
                "delay_label": f"{delay // 60}h {delay % 60:02d}m" if delay else "Nessun ritardo",
                "procedure_id": procedure.get("id") if procedure else None,
                "session_status": procedure.get("status") if procedure else None,
                "completed": completed,
            })
    missing = [item for item in expectations if not item["completed"]]
    planning_id = int(snapshot["planning"]["id"])
    result = {**empty,
        "planning_id": planning_id,
        "drivers_expected": len(drivers),
        "exceptions": exceptions,
        "missing": sorted(missing, key=lambda item: (
            0 if item["operation_type"] == "check_in" else 1,
            0 if item["status"] == "critico" else 1 if item["status"] == "in_ritardo" else 2,
            item["driver_name"],
        )),
    }
    for operation_type in ("check_out", "check_in"):
        relevant = [item for item in expectations if item["operation_type"] == operation_type]
        result[operation_type] = {
            "expected": len(relevant),
            "completed": sum(item["completed"] for item in relevant),
            "missing": sum(not item["completed"] for item in relevant),
        }
    result["procedures"] = {
        "open": sum(item.get("status") in {"generated", "opened"} for item in procedures),
        "in_progress": sum(item.get("status") == "in_progress" for item in procedures),
        "late": sum(item["status"] in {"in_ritardo", "critico"} for item in missing),
        "anomalies": sum(bool(item.get("anomaly_present")) for item in procedures),
    }
    result["decisions"] = _decision_cards(result["missing"], planning_id)
    return result
