from app.core.database import db_session
from app.core.config import SETTINGS
from app.core.tenant_schema import ensure_postgresql_bigint


def _ensure_column(conn, table: str, column: str, definition: str) -> None:
    if SETTINGS.database_backend == "postgresql":
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name=?",
            (table,),
        ).fetchall()
        columns = {row[0] for row in rows}
    else:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS attachments (
                id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                entity_id BIGINT NOT NULL,
                original_filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL UNIQUE,
                mime_type TEXT NOT NULL,
                size INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                storage_path TEXT NOT NULL UNIQUE,
                preview_available INTEGER NOT NULL DEFAULT 0,
                notes TEXT,
                organization_id TEXT
            );
            CREATE TABLE IF NOT EXISTS attachment_events (
                id TEXT PRIMARY KEY,
                attachment_id TEXT NOT NULL,
                organization_id TEXT NOT NULL,
                action TEXT NOT NULL,
                actor_user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                details TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_attachments_entity
                ON attachments(entity_type, entity_id, created_at);
            """
        )
        _ensure_column(conn, "attachments", "organization_id", "TEXT")
        ensure_postgresql_bigint(conn, "attachments", "entity_id")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_attachments_org_entity "
            "ON attachments(organization_id, entity_type, entity_id, created_at)"
        )


def _dict(row) -> dict | None:
    return {key: row[key] for key in row.keys()} if row else None


def entity_exists(
    entity_type: str,
    entity_id: int,
    organization_id: str | None = None,
) -> bool:
    organization_id = organization_id or current_organization_id()
    queries = {
        "document": "SELECT 1 FROM fleet_vehicle_documents WHERE id=? AND organization_id=?",
        "insurance": "SELECT 1 FROM fleet_insurance_policies p JOIN fleet_assets a ON a.id=p.vehicle_id WHERE p.id=? AND a.organization_id=?",
        "damage": "SELECT 1 FROM damage_cases d JOIN fleet_assets a ON a.id=d.vehicle_id WHERE d.id=? AND a.organization_id=?",
        "rental": "SELECT 1 FROM fleet_rentals WHERE id=? AND organization_id=?",
        "maintenance": "SELECT 1 FROM fleet_maintenances m JOIN fleet_assets a ON a.id=m.vehicle_id WHERE m.id=? AND a.organization_id=?",
        "vehicle": "SELECT 1 FROM fleet_assets WHERE id=? AND organization_id=?",
        "quality_scorecard": "SELECT 1 FROM dsp_quality_scorecards WHERE attachment_entity_id=? AND organization_id=?",
    }
    query = queries.get(entity_type)
    if not query:
        return False
    with db_session() as conn:
        return conn.execute(
            query, (entity_id, organization_id)
        ).fetchone() is not None


def create(values: dict) -> dict:
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO attachments (
                id, entity_type, entity_id, original_filename, stored_filename,
                mime_type, size, created_at, created_by, storage_path,
                preview_available, notes, organization_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["id"], values["entity_type"], values["entity_id"],
                values["original_filename"], values["stored_filename"],
                values["mime_type"], values["size"], values["created_at"],
                values["created_by"], values["storage_path"],
                int(values["preview_available"]), values.get("notes"),
                values["organization_id"],
            ),
        )
    return get(values["id"])  # type: ignore[return-value]


def get(attachment_id: str, organization_id: str | None = None) -> dict | None:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM attachments WHERE id = ?"
            + (" AND organization_id = ?" if organization_id else ""),
            (attachment_id, organization_id) if organization_id else (attachment_id,),
        ).fetchone()
    return _dict(row)


def document_organization_id(document_id: int) -> str | None:
    organization_id = current_organization_id()
    with db_session() as conn:
        row = conn.execute(
            "SELECT organization_id FROM fleet_vehicle_documents WHERE id=? AND organization_id=?",
            (document_id, organization_id),
        ).fetchone()
    return row["organization_id"] if row else None


def list_for_entity(entity_type: str, entity_id: int, organization_id: str) -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT * FROM attachments
            WHERE entity_type = ? AND entity_id = ? AND organization_id = ?
            ORDER BY created_at DESC
            """,
            (entity_type, entity_id, organization_id),
        ).fetchall()
    return [_dict(row) for row in rows]  # type: ignore[misc]


def list_for_vehicle(vehicle_id: int, organization_id: str) -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT * FROM attachments a
            WHERE a.organization_id = ? AND (
                  (a.entity_type = 'vehicle' AND a.entity_id = ?)
               OR (a.entity_type = 'document' AND a.entity_id IN
                    (SELECT id FROM fleet_vehicle_documents WHERE vehicle_id = ?))
               OR (a.entity_type = 'insurance' AND a.entity_id IN
                    (SELECT id FROM fleet_insurance_policies WHERE vehicle_id = ?))
               OR (a.entity_type = 'damage' AND a.entity_id IN
                    (SELECT id FROM damage_cases WHERE vehicle_id = ?))
               OR (a.entity_type = 'rental' AND a.entity_id IN
                    (SELECT id FROM fleet_rentals WHERE vehicle_id = ?))
               OR (a.entity_type = 'maintenance' AND a.entity_id IN
                    (SELECT id FROM fleet_maintenances WHERE vehicle_id = ?)))
            ORDER BY a.created_at DESC
            """,
            (organization_id, *((vehicle_id,) * 6)),
        ).fetchall()
    return [_dict(row) for row in rows]  # type: ignore[misc]


def delete(attachment_id: str, organization_id: str) -> dict | None:
    item = get(attachment_id, organization_id)
    if not item:
        return None
    with db_session() as conn:
        conn.execute(
            "DELETE FROM attachments WHERE id = ? AND organization_id = ?",
            (attachment_id, organization_id),
        )
    return item


def record_event(values: dict) -> None:
    with db_session() as conn:
        conn.execute(
            """INSERT INTO attachment_events
            (id,attachment_id,organization_id,action,actor_user_id,created_at,details)
            VALUES (?,?,?,?,?,?,?)""",
            (
                values["id"], values["attachment_id"], values["organization_id"],
                values["action"], values["actor_user_id"], values["created_at"],
                values.get("details"),
            ),
        )
from app.auth.tenant_context import current_organization_id
