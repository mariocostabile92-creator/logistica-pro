from app.core.database import db_session
from app.utils.date_utils import utc_now_iso


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS fleet_vehicle_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_id INTEGER NOT NULL,
                document_type TEXT NOT NULL,
                title TEXT NOT NULL,
                document_number TEXT,
                issuer TEXT,
                issued_at TEXT,
                expires_at TEXT,
                uploaded_at TEXT,
                notes TEXT,
                status TEXT NOT NULL,
                file_name TEXT,
                file_reference TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (vehicle_id) REFERENCES fleet_assets(id)
            );
            CREATE INDEX IF NOT EXISTS idx_vehicle_documents_vehicle
                ON fleet_vehicle_documents(vehicle_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_vehicle_documents_status
                ON fleet_vehicle_documents(status, expires_at);
            CREATE INDEX IF NOT EXISTS idx_vehicle_documents_type
                ON fleet_vehicle_documents(document_type);
            """
        )


def _dict(row):
    return {key: row[key] for key in row.keys()} if row else None


def _select() -> str:
    return """
        SELECT d.*, a.plate, a.external_identifier,
               a.category AS vehicle_model,
               p.contract_type, p.contract_number,
               (SELECT COUNT(*) FROM attachments att
                WHERE att.entity_type = 'document' AND att.entity_id = d.id)
                    AS attachment_count,
               (SELECT MAX(att.created_at) FROM attachments att
                WHERE att.entity_type = 'document' AND att.entity_id = d.id)
                    AS attachment_uploaded_at
        FROM fleet_vehicle_documents d
        JOIN fleet_assets a ON a.id = d.vehicle_id
        LEFT JOIN fleet_asset_profiles p ON p.asset_id = d.vehicle_id
    """


def get(document_id: int):
    with db_session() as conn:
        row = conn.execute(
            f"{_select()} WHERE d.id = ?",
            (document_id,),
        ).fetchone()
    return _dict(row)


def list_all(
    vehicle_id: int | None = None,
    search: str | None = None,
    status: str | None = None,
    document_type: str | None = None,
    has_file: bool | None = None,
):
    clauses: list[str] = []
    params: list[object] = []
    if vehicle_id:
        clauses.append("d.vehicle_id = ?")
        params.append(vehicle_id)
    if search:
        clauses.append(
            """(
                LOWER(COALESCE(a.plate, a.external_identifier, '')) LIKE ?
                OR LOWER(d.title) LIKE ?
                OR LOWER(COALESCE(d.document_number, '')) LIKE ?
                OR LOWER(COALESCE(d.issuer, '')) LIKE ?
                OR LOWER(d.document_type) LIKE ?
            )"""
        )
        needle = f"%{search.casefold()}%"
        params.extend([needle] * 5)
    if status:
        clauses.append("d.status = ?")
        params.append(status)
    if document_type:
        clauses.append("d.document_type = ?")
        params.append(document_type)
    if has_file is not None:
        clauses.append(
            """((d.file_reference IS NOT NULL AND d.file_reference <> '')
                OR EXISTS (SELECT 1 FROM attachments att
                           WHERE att.entity_type = 'document'
                             AND att.entity_id = d.id))"""
            if has_file else
            """((d.file_reference IS NULL OR d.file_reference = '')
                AND NOT EXISTS (SELECT 1 FROM attachments att
                                WHERE att.entity_type = 'document'
                                  AND att.entity_id = d.id))"""
        )
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with db_session() as conn:
        rows = conn.execute(
            f"""
            {_select()} {where}
            ORDER BY
              CASE d.status
                WHEN 'scaduto' THEN 0
                WHEN 'in_scadenza' THEN 1
                WHEN 'valido' THEN 2
                WHEN 'senza_scadenza' THEN 3
                ELSE 4
              END,
              COALESCE(d.expires_at, d.created_at) DESC,
              d.id DESC
            """,
            params,
        ).fetchall()
    return [_dict(row) for row in rows]


def vehicle_exists(vehicle_id: int) -> bool:
    with db_session() as conn:
        row = conn.execute(
            "SELECT id FROM fleet_assets WHERE id = ?",
            (vehicle_id,),
        ).fetchone()
    return bool(row)


def create(values: dict[str, object]):
    now = utc_now_iso()
    uploaded_at = now if values.get("file_reference") else None
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO fleet_vehicle_documents (
                vehicle_id, document_type, title, document_number, issuer,
                issued_at, expires_at, uploaded_at, notes, status,
                file_name, file_reference, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["vehicle_id"], values["document_type"], values["title"],
                values.get("document_number"), values.get("issuer"),
                values.get("issued_at"), values.get("expires_at"), uploaded_at,
                values.get("notes"), values["status"], values.get("file_name"),
                values.get("file_reference"), now, now,
            ),
        )
        document_id = int(cursor.lastrowid)
    return get(document_id)


def update(document_id: int, values: dict[str, object]):
    current = get(document_id)
    if not current:
        return None
    allowed = {
        "document_type", "title", "document_number", "issuer", "issued_at",
        "expires_at", "notes", "status", "file_name", "file_reference",
    }
    changes = {key: value for key, value in values.items() if key in allowed}
    if not changes:
        return current
    if "file_reference" in changes:
        changes["uploaded_at"] = (
            current.get("uploaded_at") or utc_now_iso()
            if changes["file_reference"] else None
        )
    changes["updated_at"] = utc_now_iso()
    with db_session() as conn:
        assignments = ", ".join(f"{key} = ?" for key in changes)
        conn.execute(
            f"UPDATE fleet_vehicle_documents SET {assignments} WHERE id = ?",
            [*changes.values(), document_id],
        )
    return get(document_id)


def fleet_summary(total_assets: int) -> dict[str, int]:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status = 'scaduto' THEN 1 ELSE 0 END) AS expired,
                   SUM(CASE WHEN status = 'in_scadenza' THEN 1 ELSE 0 END) AS expiring,
                   SUM(CASE WHEN file_reference IS NULL OR file_reference = ''
                            THEN 1 ELSE 0 END) AS missing_files,
                   COUNT(DISTINCT vehicle_id) AS documented_assets
            FROM fleet_vehicle_documents
            """
        ).fetchone()
    return {
        "total": int(row["total"] or 0),
        "expired": int(row["expired"] or 0),
        "expiring": int(row["expiring"] or 0),
        "assets_without_documents": max(
            0, total_assets - int(row["documented_assets"] or 0)
        ),
        "missing_files": int(row["missing_files"] or 0),
    }
