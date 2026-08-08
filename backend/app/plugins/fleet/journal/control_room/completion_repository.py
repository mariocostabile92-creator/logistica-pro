import json

from app.auth.tenant_context import current_organization_id
from app.core.config import SETTINGS
from app.core.database import db_session


def _rows(cursor) -> list[dict]:
    return [dict(row) for row in cursor.fetchall()]


def _scope(allow_test_legacy: bool) -> str:
    return (
        "(organization_id = ? OR organization_id IS NULL OR organization_id = 'default')"
        if SETTINGS.environment == "test" and allow_test_legacy
        else "organization_id = ?"
    )


def _planning_snapshot(
    operation_date: str,
    organization_id: str,
    *,
    authoritative_only: bool,
    allow_test_legacy: bool,
) -> dict | None:
    planning_scope = _scope(allow_test_legacy)
    asset_scope = _scope(allow_test_legacy)
    status_clause = (
        "status IN ('published', 'confirmed')"
        if authoritative_only
        else "status <> 'superseded'"
    )
    order = (
        "CASE status WHEN 'published' THEN 0 ELSE 1 END, id DESC"
        if authoritative_only
        else "id DESC"
    )
    with db_session() as conn:
        planning = conn.execute(
            f"""
            SELECT id, operation_date, station, status, version, updated_at
            FROM plannings
            WHERE operation_date = ? AND {status_clause}
              AND {planning_scope}
            ORDER BY {order}
            LIMIT 1
            """,
            (operation_date, organization_id),
        ).fetchone()
        if not planning:
            return None
        assignments = _rows(conn.execute(
            f"""
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
            f"""
            SELECT id, external_identifier, plate, category
            FROM fleet_assets
            WHERE {asset_scope}
            ORDER BY id
            """,
            (organization_id,),
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


def planning_snapshot(
    operation_date: str,
    organization_id: str | None = None,
) -> dict | None:
    explicit_organization = organization_id is not None
    return _planning_snapshot(
        operation_date,
        organization_id or current_organization_id(),
        authoritative_only=False,
        allow_test_legacy=not explicit_organization,
    )


def authoritative_planning_snapshot(
    operation_date: str,
    organization_id: str,
) -> dict | None:
    return _planning_snapshot(
        operation_date,
        organization_id,
        authoritative_only=True,
        allow_test_legacy=False,
    )
