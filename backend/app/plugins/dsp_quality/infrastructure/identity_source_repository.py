import json

from app.core.database import db_session
from app.utils.date_utils import utc_now_iso


def strict_workforce_members(organization_id: str) -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            """SELECT id, external_identifier, display_name, station, active
               FROM workforce_members WHERE organization_id = ? ORDER BY id""",
            (organization_id,),
        ).fetchall()
    return [{key: row[key] for key in row.keys()} for row in rows]


def latest_planning_source(organization_id: str) -> dict | None:
    with db_session() as conn:
        row = conn.execute(
            """SELECT i.id, i.original_filename, i.sheet_name,
                      i.normalized_rows, i.imported_at,
                      p.id AS planning_id, p.status AS planning_status,
                      p.operation_date
               FROM plannings p
               JOIN imports i ON i.id = p.source_planning_import_id
               WHERE p.organization_id = ?
                 AND i.organization_id = ?
                 AND i.dataset_type = 'planning'
               ORDER BY p.id DESC
               LIMIT 1""",
            (organization_id, organization_id),
        ).fetchone()
        if not row:
            row = conn.execute(
                """SELECT id, original_filename, sheet_name,
                          normalized_rows, imported_at,
                          NULL AS planning_id, NULL AS planning_status,
                          NULL AS operation_date
                   FROM imports
                   WHERE organization_id = ? AND dataset_type = 'planning'
                   ORDER BY id DESC
                   LIMIT 1""",
                (organization_id,),
            ).fetchone()
    if not row:
        return None
    return {
        "id": int(row["id"]),
        "original_filename": row["original_filename"],
        "sheet_name": row["sheet_name"],
        "normalized_rows": json.loads(row["normalized_rows"]),
        "imported_at": row["imported_at"],
        "planning_id": row["planning_id"],
        "planning_status": row["planning_status"],
        "operation_date": row["operation_date"],
    }


class ExactIdentityConflictError(ValueError):
    pass


def apply_exact_mappings(
    *,
    organization_id: str,
    actor: str,
    rows: list[dict],
    source: dict,
) -> dict:
    now = utc_now_iso()
    applied: list[str] = []
    already_verified = 0
    with db_session() as conn:
        for item in rows:
            member = conn.execute(
                "SELECT id, display_name FROM workforce_members WHERE id = ? AND organization_id = ?",
                (item["workforce_member_id"], organization_id),
            ).fetchone()
            if not member:
                raise ExactIdentityConflictError(
                    "Il driver Workforce proposto non appartiene all'organizzazione."
                )
            existing = conn.execute(
                """SELECT * FROM workforce_external_identities
                   WHERE organization_id = ? AND source = 'amazon_transporter' AND external_id = ?""",
                (organization_id, item["transporter_external_id"]),
            ).fetchone()
            if existing and existing["status"] == "MATCHED":
                if int(existing["workforce_member_id"]) == int(item["workforce_member_id"]):
                    already_verified += 1
                    continue
                raise ExactIdentityConflictError(
                    f"Il Transporter {item['transporter_external_id']} ha gia un mapping verificato differente."
                )
            identity_id = existing["id"] if existing else item["identity_id"]
            created_at = existing["created_at"] if existing else now
            conn.execute(
                """
                INSERT INTO workforce_external_identities (
                    id, organization_id, source, external_id, workforce_member_id,
                    status, valid_from, valid_to, verified_by, verified_at,
                    created_at, updated_at
                ) VALUES (?, ?, 'amazon_transporter', ?, ?, 'MATCHED', NULL, NULL, ?, ?, ?, ?)
                ON CONFLICT(organization_id, source, external_id) DO UPDATE SET
                    workforce_member_id=excluded.workforce_member_id,
                    status='MATCHED', verified_by=excluded.verified_by,
                    verified_at=excluded.verified_at, updated_at=excluded.updated_at
                """,
                (
                    identity_id, organization_id, item["transporter_external_id"],
                    item["workforce_member_id"], actor, now, created_at, now,
                ),
            )
            details = {
                "source": "amazon_transporter",
                "external_id": item["transporter_external_id"],
                "previous_workforce_member_id": None,
                "previous_workforce_display_name": None,
                "new_workforce_member_id": item["workforce_member_id"],
                "new_workforce_display_name": member["display_name"],
                "source_type": source["source_type"],
                "source_filename": source.get("filename"),
                "source_reference": source.get("source_reference"),
                "source_sheet": item.get("source_sheet"),
                "source_row": item.get("source_row"),
                "resolution_method": item.get("resolution_method"),
            }
            conn.execute(
                """INSERT INTO workforce_external_identity_events (
                    id, identity_id, organization_id, action, actor, details, created_at
                ) VALUES (?, ?, ?, 'mapping_created', ?, ?, ?)""",
                (
                    item["event_id"], identity_id, organization_id, actor,
                    json.dumps(details, ensure_ascii=False, sort_keys=True), now,
                ),
            )
            applied.append(item["transporter_external_id"])
    return {"applied": applied, "already_verified": already_verified}
