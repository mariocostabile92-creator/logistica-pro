from app.core.database import db_session


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS attachments (
                id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                original_filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL UNIQUE,
                mime_type TEXT NOT NULL,
                size INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                storage_path TEXT NOT NULL UNIQUE,
                preview_available INTEGER NOT NULL DEFAULT 0,
                notes TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_attachments_entity
                ON attachments(entity_type, entity_id, created_at);
            """
        )


def _dict(row) -> dict | None:
    return {key: row[key] for key in row.keys()} if row else None


def entity_exists(entity_type: str, entity_id: int) -> bool:
    tables = {
        "document": "fleet_vehicle_documents",
        "insurance": "fleet_insurance_policies",
        "damage": "damage_cases",
        "rental": "fleet_rentals",
        "maintenance": "fleet_maintenances",
        "vehicle": "fleet_assets",
    }
    table = tables.get(entity_type)
    if not table:
        return False
    with db_session() as conn:
        return conn.execute(
            f"SELECT 1 FROM {table} WHERE id = ?", (entity_id,)
        ).fetchone() is not None


def create(values: dict) -> dict:
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO attachments (
                id, entity_type, entity_id, original_filename, stored_filename,
                mime_type, size, created_at, created_by, storage_path,
                preview_available, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["id"], values["entity_type"], values["entity_id"],
                values["original_filename"], values["stored_filename"],
                values["mime_type"], values["size"], values["created_at"],
                values["created_by"], values["storage_path"],
                int(values["preview_available"]), values.get("notes"),
            ),
        )
    return get(values["id"])  # type: ignore[return-value]


def get(attachment_id: str) -> dict | None:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM attachments WHERE id = ?", (attachment_id,)
        ).fetchone()
    return _dict(row)


def document_organization_id(document_id: int) -> str | None:
    with db_session() as conn:
        row = conn.execute("SELECT organization_id FROM fleet_vehicle_documents WHERE id=?", (document_id,)).fetchone()
    return row["organization_id"] if row else None


def list_for_entity(entity_type: str, entity_id: int) -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT * FROM attachments
            WHERE entity_type = ? AND entity_id = ?
            ORDER BY created_at DESC
            """,
            (entity_type, entity_id),
        ).fetchall()
    return [_dict(row) for row in rows]  # type: ignore[misc]


def list_for_vehicle(vehicle_id: int) -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT * FROM attachments a
            WHERE (a.entity_type = 'vehicle' AND a.entity_id = ?)
               OR (a.entity_type = 'document' AND a.entity_id IN
                    (SELECT id FROM fleet_vehicle_documents WHERE vehicle_id = ?))
               OR (a.entity_type = 'insurance' AND a.entity_id IN
                    (SELECT id FROM fleet_insurance_policies WHERE vehicle_id = ?))
               OR (a.entity_type = 'damage' AND a.entity_id IN
                    (SELECT id FROM damage_cases WHERE vehicle_id = ?))
               OR (a.entity_type = 'rental' AND a.entity_id IN
                    (SELECT id FROM fleet_rentals WHERE vehicle_id = ?))
               OR (a.entity_type = 'maintenance' AND a.entity_id IN
                    (SELECT id FROM fleet_maintenances WHERE vehicle_id = ?))
            ORDER BY a.created_at DESC
            """,
            (vehicle_id,) * 6,
        ).fetchall()
    return [_dict(row) for row in rows]  # type: ignore[misc]


def delete(attachment_id: str) -> dict | None:
    item = get(attachment_id)
    if not item:
        return None
    with db_session() as conn:
        conn.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
    return item
