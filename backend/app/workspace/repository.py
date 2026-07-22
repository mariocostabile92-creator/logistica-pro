import json
from collections.abc import Sequence
from typing import Any

from app.core.database import db_session


OPERATIONAL_DELETE_ORDER = (
    "planning_publications",
    "planning_confirmations",
    "planning_draft_changes",
    "planning_draft_versions",
    "planning_drafts",
    "daily_briefings",
    "planning_events",
    "planning_versions",
    "assignments",
    "plannings",
    "operation_snapshots",
    "analyses",
    "workforce_changes",
    "workforce_day_statuses",
    "workforce_requirements",
    "workforce_members",
    "workforce_imports",
    "fleet_asset_documents",
    "fleet_sync_event_fingerprints",
    "fleet_asset_events",
    "fleet_sync_runs",
    "fleet_asset_metadata",
    "fleet_assets",
    "imports",
    "demo_workspaces",
)

PRESERVED_TABLES = (
    "configuration_versions",
    "workspace_reset_audits",
)


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS workspace_reset_audits (
                reset_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                actor TEXT NOT NULL,
                previous_state TEXT NOT NULL,
                final_state TEXT,
                removed_counts TEXT NOT NULL,
                outcome TEXT NOT NULL,
                sanitized_error TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_workspace_reset_started
                ON workspace_reset_audits(started_at);
            """
        )


def _count(conn, table: str) -> int:
    row = conn.execute(
        f"SELECT COUNT(*) AS total FROM {table}"
    ).fetchone()
    return int(row["total"]) if row else 0


def _ids(conn, statement: str, parameters: Sequence[object] = ()) -> set[int]:
    return {
        int(row["id"])
        for row in conn.execute(statement, parameters).fetchall()
    }


def _metadata_ids(metadata: dict[str, Any], key: str) -> set[int]:
    values = metadata.get(key) or []
    if not isinstance(values, list):
        values = [values]
    return {
        int(value)
        for value in values
        if isinstance(value, int) or str(value).isdigit()
    }


def _latest_import(conn, dataset_type: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, original_filename, imported_at, normalized_rows
        FROM imports
        WHERE dataset_type = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (dataset_type,),
    ).fetchone()
    if not row:
        return None
    try:
        normalized_rows = json.loads(row["normalized_rows"])
    except (TypeError, ValueError):
        normalized_rows = []
    return {
        "import_id": int(row["id"]),
        "original_filename": row["original_filename"],
        "imported_at": row["imported_at"],
        "rows_imported": (
            len(normalized_rows)
            if isinstance(normalized_rows, list)
            else 0
        ),
    }


def _active_demo(conn) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT status, updated_at, metadata
        FROM demo_workspaces
        WHERE is_demo = 1
          AND status IN ('loading', 'partial', 'ready')
        ORDER BY updated_at DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return None
    try:
        metadata = json.loads(row["metadata"])
    except (TypeError, ValueError):
        metadata = {}
    return {
        "status": row["status"],
        "updated_at": row["updated_at"],
        "metadata": metadata if isinstance(metadata, dict) else {},
    }


def _owned_demo_ids(
    conn,
    demo: dict[str, Any] | None,
) -> dict[str, set[int]]:
    if not demo:
        return {
            "imports": set(),
            "plannings": set(),
            "operation_snapshots": set(),
            "fleet_assets": set(),
            "daily_briefings": set(),
        }
    metadata = demo["metadata"]
    import_ids = _metadata_ids(metadata, "import_ids")
    planning_ids = _metadata_ids(metadata, "planning_ids")
    snapshot_ids = _metadata_ids(metadata, "operation_snapshot_ids")
    asset_ids = _metadata_ids(metadata, "asset_ids")

    if import_ids:
        placeholders = ",".join("?" for _ in import_ids)
        parameters = tuple(sorted(import_ids))
        planning_ids.update(
            _ids(
                conn,
                f"""
                SELECT id
                FROM plannings
                WHERE source_planning_import_id IN ({placeholders})
                   OR source_fleet_import_id IN ({placeholders})
                """,
                (*parameters, *parameters),
            )
        )
        snapshot_ids.update(
            _ids(
                conn,
                f"""
                SELECT id
                FROM operation_snapshots
                WHERE planning_import_id IN ({placeholders})
                   OR fleet_import_id IN ({placeholders})
                """,
                (*parameters, *parameters),
            )
        )

    briefing_ids: set[int] = set()
    if planning_ids:
        placeholders = ",".join("?" for _ in planning_ids)
        briefing_ids.update(
            _ids(
                conn,
                f"""
                SELECT id
                FROM daily_briefings
                WHERE planning_id IN ({placeholders})
                   OR is_demo = 1
                """,
                tuple(sorted(planning_ids)),
            )
        )

    return {
        "imports": import_ids,
        "plannings": planning_ids,
        "operation_snapshots": snapshot_ids,
        "fleet_assets": asset_ids,
        "daily_briefings": briefing_ids,
    }


def _latest_operational_update(conn) -> str | None:
    statements = (
        "SELECT MAX(imported_at) AS value FROM imports",
        "SELECT MAX(created_at) AS value FROM analyses",
        "SELECT MAX(created_at) AS value FROM operation_snapshots",
        "SELECT MAX(updated_at) AS value FROM plannings",
        "SELECT MAX(updated_at) AS value FROM fleet_assets",
        "SELECT MAX(imported_at) AS value FROM workforce_imports",
        "SELECT MAX(updated_at) AS value FROM workforce_members",
        "SELECT MAX(imported_at) AS value FROM fleet_sync_runs",
        "SELECT MAX(generated_at) AS value FROM daily_briefings",
        "SELECT MAX(updated_at) AS value FROM demo_workspaces",
    )
    values = []
    for statement in statements:
        row = conn.execute(statement).fetchone()
        if row and row["value"]:
            values.append(str(row["value"]))
    return max(values) if values else None


def read_inventory() -> dict[str, Any]:
    with db_session() as conn:
        counts = {
            table: _count(conn, table)
            for table in OPERATIONAL_DELETE_ORDER
        }
        latest_planning = _latest_import(conn, "planning")
        latest_fleet = _latest_import(conn, "fleet")
        demo = _active_demo(conn)
        owned = _owned_demo_ids(conn, demo)
        all_ids = {
            "imports": _ids(conn, "SELECT id FROM imports"),
            "plannings": _ids(conn, "SELECT id FROM plannings"),
            "operation_snapshots": _ids(
                conn,
                "SELECT id FROM operation_snapshots",
            ),
            "fleet_assets": _ids(conn, "SELECT id FROM fleet_assets"),
            "daily_briefings": _ids(
                conn,
                "SELECT id FROM daily_briefings",
            ),
        }
        non_demo_relational_data = any(
            all_ids[table] - owned[table]
            for table in all_ids
        )
        analyses_are_demo_derived = bool(
            demo
            and all_ids["imports"]
            and all_ids["imports"] <= owned["imports"]
            and not non_demo_relational_data
        )
        non_demo_data = (
            non_demo_relational_data
            or counts["workforce_members"] > 0
            or counts["workforce_day_statuses"] > 0
            or counts["workforce_imports"] > 0
            or (
                counts["analyses"] > 0
                and not analyses_are_demo_derived
            )
        )
        has_operational_data = any(
            counts[table] > 0
            for table in (
                "imports",
                "analyses",
                "operation_snapshots",
                "plannings",
                "fleet_assets",
                "workforce_members",
                "workforce_day_statuses",
                "workforce_imports",
                "fleet_sync_runs",
                "daily_briefings",
            )
        )
        asset_count = max(
            counts["fleet_assets"],
            latest_fleet["rows_imported"] if latest_fleet else 0,
        )
        return {
            "counts": counts,
            "latest_planning_import": latest_planning,
            "latest_fleet_import": latest_fleet,
            "task_count": (
                latest_planning["rows_imported"]
                if latest_planning
                else 0
            ),
            "asset_count": asset_count,
            "workforce_member_count": counts["workforce_members"],
            "planning_count": counts["plannings"],
            "briefing_count": counts["daily_briefings"],
            "last_operational_update": _latest_operational_update(conn),
            "active_demo": demo is not None,
            "has_operational_data": has_operational_data,
            "non_demo_data": non_demo_data,
        }


def reset_operational_data(conn) -> dict[str, int]:
    removed = {
        table: _count(conn, table)
        for table in OPERATIONAL_DELETE_ORDER
    }
    for table in OPERATIONAL_DELETE_ORDER:
        conn.execute(f"DELETE FROM {table}")
    return removed


def start_reset_audit(
    *,
    reset_id: str,
    started_at: str,
    actor: str,
    previous_state: str,
) -> None:
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO workspace_reset_audits (
                reset_id, started_at, actor, previous_state,
                removed_counts, outcome
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                reset_id,
                started_at,
                actor,
                previous_state,
                "{}",
                "started",
            ),
        )


def complete_reset_audit(
    *,
    reset_id: str,
    completed_at: str,
    final_state: str,
    removed_counts: dict[str, int],
    outcome: str,
    sanitized_error: str | None = None,
) -> None:
    with db_session() as conn:
        conn.execute(
            """
            UPDATE workspace_reset_audits
            SET completed_at = ?, final_state = ?, removed_counts = ?,
                outcome = ?, sanitized_error = ?
            WHERE reset_id = ?
            """,
            (
                completed_at,
                final_state,
                json.dumps(removed_counts, sort_keys=True),
                outcome,
                sanitized_error,
                reset_id,
            ),
        )


def get_reset_audit(reset_id: str) -> dict[str, Any] | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM workspace_reset_audits
            WHERE reset_id = ?
            """,
            (reset_id,),
        ).fetchone()
    if not row:
        return None
    return {
        **{key: row[key] for key in row.keys()},
        "removed_counts": json.loads(row["removed_counts"]),
    }
