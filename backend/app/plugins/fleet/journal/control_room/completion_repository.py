import json

from app.core.database import db_session


def _rows(cursor) -> list[dict]:
    return [dict(row) for row in cursor.fetchall()]


def planning_snapshot(operation_date: str) -> dict | None:
    with db_session() as conn:
        planning = conn.execute(
            """
            SELECT id, operation_date, station, status, version, updated_at
            FROM plannings
            WHERE operation_date = ? AND status <> 'superseded'
            ORDER BY id DESC
            LIMIT 1
            """,
            (operation_date,),
        ).fetchone()
        if not planning:
            return None
        assignments = _rows(conn.execute(
            """
            SELECT id, planning_id, route_id, cycle_or_wave, driver_id,
                   driver_name, vehicle_id, plate, assignment_status,
                   warnings, reasons, notes, confirmed, updated_at
            FROM assignments
            WHERE planning_id = ?
            ORDER BY route_id, id
            """,
            (planning["id"],),
        ))
        events = _rows(conn.execute(
            """
            SELECT event_type, entity_type, entity_id, applied, payload, diff
            FROM planning_events
            WHERE planning_id = ? AND applied = 1
            ORDER BY id
            """,
            (planning["id"],),
        ))
        assets = _rows(conn.execute(
            """
            SELECT id, external_identifier, plate, category
            FROM fleet_assets
            ORDER BY id
            """
        ))
    for assignment in assignments:
        for key in ("warnings", "reasons"):
            value = assignment.get(key)
            decoded = value if isinstance(value, list) else json.loads(str(value or "[]"))
            assignment[key] = decoded if isinstance(decoded, list) else []
    return {
        "planning": dict(planning),
        "assignments": assignments,
        "events": events,
        "assets": assets,
    }
