import json

from app.core.database import db_session


def _dict(row) -> dict | None:
    return {key: row[key] for key in row.keys()} if row else None


def current_identity(organization_id: str, external_id: str) -> dict | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT identity.*, member.display_name AS workforce_display_name
            FROM workforce_external_identities identity
            LEFT JOIN workforce_members member
              ON member.id = identity.workforce_member_id
             AND member.organization_id = identity.organization_id
            WHERE identity.organization_id = ?
              AND identity.source = 'amazon_transporter'
              AND identity.external_id = ?
            """,
            (organization_id, external_id),
        ).fetchone()
    return _dict(row)


def identity_metadata(organization_id: str, external_ids: list[str]) -> dict[str, dict]:
    identifiers = sorted({item.strip() for item in external_ids if item.strip()})
    if not identifiers:
        return {}
    placeholders = ",".join("?" for _ in identifiers)
    with db_session() as conn:
        rows = conn.execute(
            f"""
            SELECT identity.external_id, identity.status,
                   identity.workforce_member_id, identity.verified_at,
                   identity.verified_by, identity.updated_at,
                   member.display_name AS workforce_display_name
            FROM workforce_external_identities identity
            LEFT JOIN workforce_members member
              ON member.id = identity.workforce_member_id
             AND member.organization_id = identity.organization_id
            WHERE identity.organization_id = ?
              AND identity.source = 'amazon_transporter'
              AND identity.external_id IN ({placeholders})
            """,
            (organization_id, *identifiers),
        ).fetchall()
    return {row["external_id"]: _dict(row) for row in rows}


def history(organization_id: str, external_id: str) -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT event.action, event.actor, event.details, event.created_at
            FROM workforce_external_identity_events event
            JOIN workforce_external_identities identity
              ON identity.id = event.identity_id
             AND identity.organization_id = event.organization_id
            WHERE event.organization_id = ?
              AND identity.source = 'amazon_transporter'
              AND identity.external_id = ?
              AND event.action IN (
                'mapping_created', 'mapping_replaced', 'mapping_removed'
              )
            ORDER BY event.created_at DESC, event.id DESC
            """,
            (organization_id, external_id),
        ).fetchall()
    result = []
    for row in rows:
        item = _dict(row)
        details = json.loads(item.pop("details") or "{}")
        item.update(details)
        result.append(item)
    return result

