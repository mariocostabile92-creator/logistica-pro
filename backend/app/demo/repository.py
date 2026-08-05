import json
from collections.abc import Mapping, Sequence
from typing import Any

from app.auth.tenant_context import current_organization_id
from app.core.database import db_session
from app.core.tenant_schema import ensure_column


ImportRecoverySignature = tuple[str, str, frozenset[str]]


def _scoped_workspace_id(demo_workspace_id: str, organization_id: str) -> str:
    return f"{organization_id}:{demo_workspace_id}"


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS demo_workspaces (
                demo_workspace_id TEXT PRIMARY KEY,
                organization_id TEXT,
                dataset_version TEXT NOT NULL,
                is_demo INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                reset_at TEXT,
                metadata TEXT NOT NULL
            );
            """
        )
        ensure_column(conn, "demo_workspaces", "organization_id", "TEXT")
        owner = conn.execute(
            "SELECT id FROM organizations ORDER BY created_at ASC, id ASC LIMIT 1"
        ).fetchone()
        if owner:
            conn.execute(
                """
                UPDATE demo_workspaces SET organization_id=?
                WHERE organization_id IS NULL OR organization_id='default'
                """,
                (owner["id"],),
            )
        conn.execute(
            """
            UPDATE demo_workspaces
            SET demo_workspace_id = organization_id || ':' || demo_workspace_id
            WHERE organization_id IS NOT NULL
              AND demo_workspace_id NOT LIKE organization_id || ':%'
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_demo_workspace_organization "
            "ON demo_workspaces(organization_id, updated_at)"
        )


def get_workspace(demo_workspace_id: str) -> dict[str, Any] | None:
    organization_id = current_organization_id()
    storage_id = _scoped_workspace_id(demo_workspace_id, organization_id)
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM demo_workspaces
            WHERE demo_workspace_id = ? AND organization_id = ?
            """,
            (storage_id, organization_id),
        ).fetchone()
    if row is None:
        return None
    return {
        "demo_workspace_id": demo_workspace_id,
        "dataset_version": row["dataset_version"],
        "is_demo": bool(row["is_demo"]),
        "status": row["status"],
        "created_at": row["created_at"],
        "created_by": row["created_by"],
        "updated_at": row["updated_at"],
        "reset_at": row["reset_at"],
        "metadata": json.loads(row["metadata"]),
    }


def save_workspace(
    *,
    demo_workspace_id: str,
    dataset_version: str,
    status: str,
    created_at: str,
    created_by: str,
    updated_at: str,
    metadata: dict[str, Any],
    reset_at: str | None = None,
) -> None:
    organization_id = current_organization_id()
    storage_id = _scoped_workspace_id(demo_workspace_id, organization_id)
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO demo_workspaces (
                demo_workspace_id, organization_id, dataset_version, is_demo, status,
                created_at, created_by, updated_at, reset_at, metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (demo_workspace_id) DO UPDATE SET
                dataset_version = excluded.dataset_version,
                is_demo = excluded.is_demo,
                status = excluded.status,
                created_at = excluded.created_at,
                created_by = excluded.created_by,
                updated_at = excluded.updated_at,
                reset_at = excluded.reset_at,
                metadata = excluded.metadata
            """,
            (
                storage_id,
                organization_id,
                dataset_version,
                1,
                status,
                created_at,
                created_by,
                updated_at,
                reset_at,
                json.dumps(metadata, ensure_ascii=False),
            ),
        )


def _integer_ids(metadata: dict[str, Any], key: str) -> set[int]:
    values = metadata.get(key) or []
    if not isinstance(values, list):
        values = [values]
    return {
        int(value)
        for value in values
        if isinstance(value, int) or str(value).isdigit()
    }


def _select_ids(
    conn,
    statement: str,
    parameters: Sequence[object],
) -> set[int]:
    return {
        int(row["id"])
        for row in conn.execute(statement, parameters).fetchall()
    }


def _delete_ids(conn, table: str, ids: set[int]) -> int:
    if not ids:
        return 0
    allowed_tables = {
        "fleet_assets",
        "imports",
        "operation_snapshots",
        "plannings",
    }
    if table not in allowed_tables:
        raise ValueError("Tabella demo non consentita.")
    placeholders = ",".join("?" for _ in ids)
    organization_id = current_organization_id()
    existing_ids = _select_ids(
        conn,
        f"SELECT id FROM {table} WHERE id IN ({placeholders}) AND organization_id = ?",
        (*tuple(sorted(ids)), organization_id),
    )
    if not existing_ids:
        return 0
    placeholders = ",".join("?" for _ in existing_ids)
    conn.execute(
        f"DELETE FROM {table} WHERE id IN ({placeholders}) AND organization_id = ?",
        (*tuple(sorted(existing_ids)), organization_id),
    )
    return len(existing_ids)


def demo_entities_complete(metadata: dict[str, Any]) -> bool:
    import_ids = _integer_ids(metadata, "import_ids")
    asset_ids = _integer_ids(metadata, "asset_ids")
    planning_ids = _integer_ids(metadata, "planning_ids")
    if len(import_ids) != 2 or len(asset_ids) != 11 or len(planning_ids) != 1:
        return False
    with db_session() as conn:
        organization_id = current_organization_id()
        for table, ids in (
            ("imports", import_ids),
            ("fleet_assets", asset_ids),
            ("plannings", planning_ids),
        ):
            placeholders = ",".join("?" for _ in ids)
            row = conn.execute(
                f"SELECT COUNT(*) AS total FROM {table} "
                f"WHERE id IN ({placeholders}) AND organization_id = ?",
                (*tuple(sorted(ids)), organization_id),
            ).fetchone()
            if not row or int(row["total"]) != len(ids):
                return False
        planning_id = next(iter(planning_ids))
        assignment_count = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM assignments
            WHERE planning_id = ?
            """,
            (planning_id,),
        ).fetchone()
        event_count = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM planning_events
            WHERE planning_id = ?
            """,
            (planning_id,),
        ).fetchone()
        if (
            not assignment_count
            or int(assignment_count["total"]) != 10
            or not event_count
            or int(event_count["total"]) < 1
        ):
            return False
    return True


def _recover_import_ids(
    conn,
    signatures: Mapping[str, ImportRecoverySignature],
) -> set[int]:
    if not signatures:
        return set()
    placeholders = ",".join("?" for _ in signatures)
    organization_id = current_organization_id()
    rows = conn.execute(
        f"""
        SELECT id, dataset_type, original_filename, normalized_rows
        FROM imports
        WHERE original_filename IN ({placeholders})
          AND organization_id = ?
        """,
        (*tuple(signatures), organization_id),
    ).fetchall()
    recovered: set[int] = set()
    for row in rows:
        signature = signatures.get(row["original_filename"])
        if not signature:
            continue
        dataset_type, identity_field, expected_values = signature
        if row["dataset_type"] != dataset_type:
            continue
        try:
            normalized_rows = json.loads(row["normalized_rows"])
        except (TypeError, ValueError):
            continue
        if not isinstance(normalized_rows, list):
            continue
        observed_values = [
            str(item.get(identity_field) or "")
            for item in normalized_rows
            if isinstance(item, dict)
        ]
        if (
            len(observed_values) == len(expected_values)
            and len(normalized_rows) == len(expected_values)
            and set(observed_values) == expected_values
        ):
            recovered.add(int(row["id"]))
    return recovered


def remove_demo_entities(
    metadata: dict[str, Any],
    *,
    import_signatures: Mapping[str, ImportRecoverySignature],
    asset_external_identifiers: Sequence[str],
    actor: str,
) -> dict[str, int]:
    organization_id = current_organization_id()
    with db_session() as conn:
        import_ids = _integer_ids(metadata, "import_ids")
        import_ids.update(_recover_import_ids(conn, import_signatures))

        asset_ids = _integer_ids(metadata, "asset_ids")
        if asset_external_identifiers:
            placeholders = ",".join(
                "?" for _ in asset_external_identifiers
            )
            asset_ids.update(
                _select_ids(
                    conn,
                    f"""
                    SELECT DISTINCT fleet_assets.id
                    FROM fleet_assets
                    JOIN fleet_asset_events
                      ON fleet_asset_events.asset_id = fleet_assets.id
                    WHERE fleet_assets.external_identifier
                          IN ({placeholders})
                      AND fleet_asset_events.actor = ?
                      AND fleet_asset_events.event_type = 'AssetCreated'
                      AND fleet_assets.organization_id = ?
                    """,
                    (*asset_external_identifiers, actor, organization_id),
                )
            )

        planning_ids = _integer_ids(metadata, "planning_ids")
        snapshot_ids = _integer_ids(metadata, "operation_snapshot_ids")
        if import_ids:
            placeholders = ",".join("?" for _ in import_ids)
            import_parameters = tuple(sorted(import_ids))
            planning_ids.update(
                _select_ids(
                    conn,
                    f"""
                    SELECT id
                    FROM plannings
                    WHERE (
                        source_planning_import_id IN ({placeholders})
                        OR source_fleet_import_id IN ({placeholders})
                    ) AND organization_id = ?
                    """,
                    (*import_parameters, *import_parameters, organization_id),
                )
            )
            snapshot_ids.update(
                _select_ids(
                    conn,
                    f"""
                    SELECT id
                    FROM operation_snapshots
                    WHERE (
                        planning_import_id IN ({placeholders})
                        OR fleet_import_id IN ({placeholders})
                    ) AND organization_id = ?
                    """,
                    (*import_parameters, *import_parameters, organization_id),
                )
            )

        removed = {
            "operation_snapshots": _delete_ids(
                conn,
                "operation_snapshots",
                snapshot_ids,
            ),
            "plannings": _delete_ids(conn, "plannings", planning_ids),
            "fleet_assets": _delete_ids(conn, "fleet_assets", asset_ids),
            "imports": _delete_ids(conn, "imports", import_ids),
        }
    return removed
