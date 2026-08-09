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

