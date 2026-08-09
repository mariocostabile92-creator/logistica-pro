from app.core.database import db_session
from app.plugins.fleet.journal.control_room import completion_repository


def authoritative_planning_snapshot(
    operation_date: str,
    organization_id: str,
) -> dict | None:
    """Reuse the operational Planning authority contract without mutations."""
    return completion_repository.authoritative_planning_snapshot(
        operation_date,
        organization_id,
    )


def compact_fleet_assets(organization_id: str) -> list[dict]:
    """Load only identity and current operational fields for this tenant."""
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT id, external_identifier, plate, category,
                   availability, status, updated_at
            FROM fleet_assets
            WHERE organization_id = ?
            ORDER BY plate, id
            """,
            (organization_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def organization_clock(organization_id: str) -> dict:
    """Read the operational clock without invoking Journal maintenance flows."""
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT timezone, operational_day_start_hour
            FROM organizations
            WHERE id = ?
            """,
            (organization_id,),
        ).fetchone()
    if not row:
        return {"timezone": "Europe/Rome", "operational_day_start_hour": 4}
    return {
        "timezone": str(row["timezone"] or "Europe/Rome"),
        "operational_day_start_hour": int(row["operational_day_start_hour"] or 4),
    }


def compact_journal_records(
    operation_date: str,
    organization_id: str,
    asset_ids: list[int],
) -> list[dict]:
    """Batch-load only Journal identity, lifecycle and anomaly fields."""
    if not asset_ids:
        return []
    unique_asset_ids = sorted(set(int(asset_id) for asset_id in asset_ids))
    placeholders = ",".join("?" for _ in unique_asset_ids)
    with db_session() as conn:
        rows = conn.execute(
            f"""
            SELECT s.id AS session_id,
                   s.asset_id,
                   COALESCE(m.declared_driver_identifier,
                            s.declared_driver_identifier) AS driver_identifier,
                   s.operation_type,
                   s.status AS session_status,
                   s.lifecycle_status,
                   s.scheduled_at,
                   s.created_at,
                   m.id AS movement_id,
                   m.occurred_at,
                   COALESCE(m.anomaly_present, 0) AS anomaly_present
            FROM journal_sessions s
            JOIN fleet_assets a ON a.id = s.asset_id
            LEFT JOIN asset_movements m ON m.session_id = s.id
            WHERE s.organization_id = ?
              AND a.organization_id = ?
              AND s.operational_date = ?
              AND s.asset_id IN ({placeholders})
            ORDER BY s.asset_id, driver_identifier, s.operation_type,
                     COALESCE(m.occurred_at, s.created_at), s.id
            """,
            (organization_id, organization_id, operation_date, *unique_asset_ids),
        ).fetchall()
    return [dict(row) for row in rows]


def compact_open_damage_cases(
    organization_id: str,
    asset_ids: list[int],
    workforce_member_ids: list[int],
) -> list[dict]:
    """Batch-load current open Damage facts for the planned rows."""
    unique_asset_ids = sorted(set(int(asset_id) for asset_id in asset_ids))
    unique_member_ids = sorted(set(int(member_id) for member_id in workforce_member_ids))
    scopes: list[str] = []
    params: list[object] = [organization_id]
    if unique_asset_ids:
        scopes.append(
            f"c.vehicle_id IN ({','.join('?' for _ in unique_asset_ids)})"
        )
        params.extend(unique_asset_ids)
    if unique_member_ids:
        scopes.append(
            "c.driver_workforce_member_id IN "
            f"({','.join('?' for _ in unique_member_ids)})"
        )
        params.extend(unique_member_ids)
    if not scopes:
        return []
    with db_session() as conn:
        rows = conn.execute(
            f"""
            SELECT c.id, c.vehicle_id, c.driver_workforce_member_id,
                   c.status, c.severity, c.vehicle_operational_status,
                   c.occurred_at
            FROM damage_cases c
            JOIN fleet_assets a ON a.id = c.vehicle_id
            WHERE a.organization_id = ?
              AND c.status NOT IN ('chiusa', 'annullata')
              AND ({' OR '.join(scopes)})
            ORDER BY c.vehicle_id, c.occurred_at, c.id
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]
