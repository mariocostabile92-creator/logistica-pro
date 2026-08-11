from app.core.database import db_session


def contact_coverage_rows(organization_id: str) -> dict[str, object]:
    with db_session() as conn:
        members = conn.execute(
            """SELECT active, phone, email
               FROM workforce_members
               WHERE organization_id=?""",
            (organization_id,),
        ).fetchall()
        planning = conn.execute(
            """SELECT id, version
               FROM driver_shift_plannings
               WHERE organization_id=? AND status='ACTIVE'
               ORDER BY updated_at DESC, id DESC LIMIT 1""",
            (organization_id,),
        ).fetchone()
        recipients = []
        if planning is not None:
            recipients = conn.execute(
                """SELECT DISTINCT m.id, m.phone, m.email
                   FROM driver_shift_planning_published_rows pr
                   JOIN workforce_members m
                     ON m.id=pr.workforce_member_id
                    AND m.organization_id=pr.organization_id
                   WHERE pr.organization_id=?
                     AND pr.driver_shift_planning_id=?
                     AND pr.planning_version=?""",
                (organization_id, planning["id"], planning["version"]),
            ).fetchall()
    return {
        "members": [dict(row) for row in members],
        "planning": dict(planning) if planning is not None else None,
        "recipients": [dict(row) for row in recipients],
    }
