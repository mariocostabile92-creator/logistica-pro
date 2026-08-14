from app.auth.tenant_context import current_organization_id
from app.core.database import db_session
from app.domain.planning_models import PlanningStatus
from app.repositories.assignment_repository import get_assignments
from app.repositories.import_repository import get_latest_import, save_import
from app.repositories.planning_repository import (
    get_planning_record,
    get_planning_record_for_date,
    list_versions,
    save_version,
    update_planning_record,
)
from app.schemas.planning_operations_schema import ForecastRequest
from app.services.planning_generation_service import get_planning_bundle
from app.utils.date_utils import utc_now_iso
from app.workspace.status_service import ensure_real_data_write_allowed


class PlanningOperationError(ValueError):
    pass


def save_forecast(request: ForecastRequest) -> dict[str, object]:
    ensure_real_data_write_allowed()
    rows = [
        {
            "operation_date": day.operation_date,
            "routes_expected": day.routes_expected,
            "station": request.station,
        }
        for day in request.days
    ]
    import_id = save_import(
        "forecast",
        request.source_filename,
        None,
        [],
        rows,
    )
    return {"import_id": import_id, "days": rows}


def forecast_snapshot() -> dict[str, object] | None:
    item = get_latest_import("forecast")
    if not item:
        return None
    return {
        "period_start": min(
            (row["operation_date"] for row in item["normalized_rows"]),
            default=None,
        ),
        "period_end": max(
            (row["operation_date"] for row in item["normalized_rows"]),
            default=None,
        ),
        "updated_at": item["imported_at"],
        "source_filename": item["original_filename"],
        "days": item["normalized_rows"],
    }


def _convocations(planning_id: int) -> list[dict[str, object]]:
    organization_id = current_organization_id()
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT c.*, a.route_id, a.driver_id, a.driver_name, a.plate,
                   a.station, a.cycle_or_wave
            FROM planning_convocations c
            JOIN assignments a ON a.id = c.assignment_id
            JOIN plannings p ON p.id=c.planning_id
            WHERE c.planning_id = ? AND p.organization_id = ?
            ORDER BY a.cycle_or_wave, a.route_id
            """,
            (planning_id, organization_id),
        ).fetchall()
    return [{key: row[key] for key in row.keys()} for row in rows]


def ensure_convocations(planning_id: int, actor: str = "system") -> None:
    now = utc_now_iso()
    assignments = get_assignments(planning_id)
    with db_session() as conn:
        for assignment in assignments:
            conn.execute(
                """
                INSERT INTO planning_convocations (
                    planning_id, assignment_id, status, scheduled_time,
                    updated_at, updated_by
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(planning_id, assignment_id) DO NOTHING
                """,
                (
                    planning_id,
                    assignment.id,
                    "da_preparare",
                    assignment.cycle_or_wave,
                    now,
                    actor,
                ),
            )


def update_convocation(
    planning_id: int,
    assignment_id: int,
    *,
    status: str,
    scheduled_time: str | None,
    actor: str,
) -> dict[str, object]:
    if not get_planning_record(planning_id):
        raise PlanningOperationError("Planning non trovato.")
    ensure_convocations(planning_id, actor)
    now = utc_now_iso()
    with db_session() as conn:
        cursor = conn.execute(
            """
            UPDATE planning_convocations
            SET status = ?, scheduled_time = ?, updated_at = ?, updated_by = ?
            WHERE planning_id = ? AND assignment_id = ?
            """,
            (status, scheduled_time, now, actor, planning_id, assignment_id),
        )
        if cursor.rowcount != 1:
            raise PlanningOperationError("Convocazione non trovata.")
    record = get_planning_record(planning_id)
    if record:
        version = record["planning"].version + 1
        record["planning"].version = version
        record["planning"].updated_at = now
        update_planning_record(
            record["planning"], record["summary"], record["conflicts"],
            record["generation_metadata"],
        )
        save_version(
            planning_id,
            version,
            "convocation_updated",
            {"assignment_id": assignment_id, "status": status},
            actor,
        )
    return next(
        item for item in _convocations(planning_id)
        if item["assignment_id"] == assignment_id
    )


def operational_snapshot(
    *,
    operation_date: str,
    can_write: bool,
    is_admin: bool,
) -> dict[str, object]:
    record = get_planning_record_for_date(operation_date)
    forecast = forecast_snapshot()
    if not record:
        legacy_expected = next(
            (
                row["routes_expected"]
                for row in (forecast or {}).get("days", [])
                if row["operation_date"] == operation_date
            ),
            None,
        )
        return {
            "operation_date": operation_date,
            "planning": None,
            "summary": {
                "routes_forecast": legacy_expected,
                "routes_definitive": None,
                "drivers_assigned": None,
                "vehicles_assigned": None,
                "routes_complete": None,
                "routes_incomplete": None,
                "conflicts": None,
                "blocking_conflicts": None,
                "convocations_ready": None,
            },
            "routes": [], "conflicts": [], "convocations": [],
            "forecast": forecast,
            "route_data_available": False,
            "vehicle_assignments_available": False,
            "lifecycle": {
                "state": "routes_missing",
                "can_confirm": False,
                "can_publish": False,
                "disabled_reason": "Importa le rotte definitive per attivare conferma e pubblicazione.",
            },
            "audit": [],
            "permissions": {"write": can_write, "diagnostics": is_admin},
        }
    planning = record["planning"]
    bundle = get_planning_bundle(planning.id)
    ensure_convocations(planning.id)
    convocations = _convocations(planning.id)
    convocation_by_assignment = {item["assignment_id"]: item for item in convocations}
    routes = []
    for assignment in bundle.assignments:
        conflicts = [
            item.model_dump(mode="json") for item in bundle.conflicts
            if item.entity_ref == assignment.route_id
        ]
        routes.append({
            **assignment.model_dump(mode="json"),
            "conflicts": conflicts,
            "convocation": convocation_by_assignment.get(assignment.id),
            "complete": bool(assignment.driver_id and assignment.plate and not any(item["blocking"] for item in conflicts)),
        })
    complete = sum(1 for route in routes if route["complete"])
    blocking = sum(1 for item in bundle.conflicts if item.blocking or item.severity == "critical")
    expected = 0
    if forecast:
        expected = next((row["routes_expected"] for row in forecast["days"] if row["operation_date"] == planning.operation_date), 0)
    status = planning.status.value
    return {
        "operation_date": operation_date,
        "planning": planning.model_dump(mode="json"),
        "summary": {
            "routes_forecast": expected,
            "routes_definitive": len(routes),
            "drivers_assigned": sum(1 for item in routes if item["driver_id"]),
            "vehicles_assigned": sum(1 for item in routes if item["plate"]),
            "routes_complete": complete,
            "routes_incomplete": len(routes) - complete,
            "conflicts": len(bundle.conflicts),
            "blocking_conflicts": blocking,
            "convocations_ready": sum(1 for item in convocations if item["status"] in {"pronta", "inviata", "confermata"}),
        },
        "routes": routes,
        "conflicts": [item.model_dump(mode="json") for item in bundle.conflicts],
        "convocations": convocations,
        "forecast": forecast,
        "route_data_available": True,
        "vehicle_assignments_available": True,
        "lifecycle": {
            "state": status,
            "can_confirm": complete == len(routes) and blocking == 0 and bool(routes) and status not in {"confirmed", "published"},
            "can_publish": status == "confirmed",
            "disabled_reason": None,
        },
        "audit": list_versions(planning.id)[-20:][::-1],
        "permissions": {"write": can_write, "diagnostics": is_admin},
    }


def transition(planning_id: int, target: str, actor: str) -> dict[str, object]:
    record = get_planning_record(planning_id)
    if not record:
        raise PlanningOperationError("Planning non trovato.")
    bundle = get_planning_bundle(planning_id)
    incomplete = [item for item in bundle.assignments if not item.driver_id or not item.plate]
    blocking = [item for item in bundle.conflicts if item.blocking or item.severity == "critical"]
    if target == "confirmed" and (incomplete or blocking):
        raise PlanningOperationError("Completa le assegnazioni e risolvi i conflitti bloccanti.")
    if target == "published" and record["planning"].status != PlanningStatus.CONFIRMED:
        raise PlanningOperationError("Il piano deve essere confermato prima della pubblicazione.")
    planning = record["planning"]
    planning.status = PlanningStatus(target)
    planning.version += 1
    planning.updated_at = utc_now_iso()
    update_planning_record(planning, record["summary"], record["conflicts"], record["generation_metadata"])
    save_version(planning_id, planning.version, f"planning_{target}", {"status": target}, actor)
    return {"planning_id": planning_id, "status": target, "version": planning.version}
