from app.core.database import db_session


def driver_exists(organization_id: str, workforce_member_id: int) -> bool:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM workforce_members
            WHERE organization_id = ? AND id = ?
            """,
            (organization_id, workforce_member_id),
        ).fetchone()
    return row is not None


def list_attributed_cases(
    organization_id: str,
    workforce_member_id: int,
) -> list[dict[str, object]]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.occurred_at, c.status, c.driver_workforce_member_id
            FROM damage_cases c
            JOIN fleet_assets a ON a.id = c.vehicle_id
            WHERE a.organization_id = ?
              AND c.driver_workforce_member_id = ?
            ORDER BY c.occurred_at ASC, c.id ASC
            """,
            (organization_id, workforce_member_id),
        ).fetchall()
    return [
        {key: row[key] for key in row.keys()}
        for row in rows
    ]

