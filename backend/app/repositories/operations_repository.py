import json
from typing import Any

from app.auth.tenant_context import current_organization_id
from app.core.database import db_session
from app.utils.date_utils import utc_now_iso


def save_operation_snapshot(
    dashboard: dict[str, Any],
    planning_import_id: int,
    fleet_import_id: int,
    reserve_threshold: int,
) -> int:
    organization_id = current_organization_id()
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO operation_snapshots (
                organization_id, created_at, planning_import_id, fleet_import_id,
                reserve_threshold, payload
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                organization_id,
                utc_now_iso(),
                planning_import_id,
                fleet_import_id,
                reserve_threshold,
                json.dumps(dashboard, ensure_ascii=False),
            ),
        )
        return int(cursor.lastrowid)


def get_latest_operation_snapshot() -> dict[str, Any] | None:
    organization_id = current_organization_id()
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM operation_snapshots
            WHERE organization_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (organization_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "planning_import_id": row["planning_import_id"],
        "fleet_import_id": row["fleet_import_id"],
        "reserve_threshold": row["reserve_threshold"],
        "payload": json.loads(row["payload"]),
    }
