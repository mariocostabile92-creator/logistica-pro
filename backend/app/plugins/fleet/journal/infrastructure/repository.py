import sqlite3

from app.core.database import db_session


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS journal_sessions (
                id TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL,
                operation_type TEXT NOT NULL,
                asset_id INTEGER NOT NULL,
                plate_snapshot TEXT NOT NULL,
                declared_driver_identifier TEXT NOT NULL,
                operational_shift TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY (asset_id) REFERENCES fleet_assets(id)
            );
            CREATE TABLE IF NOT EXISTS asset_movements (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL UNIQUE,
                schema_version TEXT NOT NULL,
                organization_id TEXT NOT NULL,
                operational_unit_id TEXT NOT NULL,
                asset_id INTEGER NOT NULL,
                plate_snapshot TEXT NOT NULL,
                declared_driver_identifier TEXT NOT NULL,
                operation_type TEXT NOT NULL,
                operational_shift TEXT,
                occurred_at TEXT NOT NULL,
                timezone TEXT NOT NULL,
                odometer_km INTEGER NOT NULL,
                fuel_percentage INTEGER NOT NULL,
                cleanliness_status TEXT,
                anomaly_present INTEGER NOT NULL,
                anomaly_description TEXT,
                operational_note TEXT,
                client_submission_id TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES journal_sessions(id),
                FOREIGN KEY (asset_id) REFERENCES fleet_assets(id)
            );
            CREATE TABLE IF NOT EXISTS movement_equipment (
                movement_id TEXT NOT NULL,
                equipment_code TEXT NOT NULL,
                equipment_label_snapshot TEXT NOT NULL,
                equipment_status TEXT NOT NULL,
                note TEXT,
                PRIMARY KEY (movement_id, equipment_code),
                FOREIGN KEY (movement_id) REFERENCES asset_movements(id)
            );
            CREATE TABLE IF NOT EXISTS movement_media (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                movement_id TEXT,
                media_type TEXT NOT NULL,
                phase TEXT NOT NULL,
                storage_key TEXT NOT NULL UNIQUE,
                verified_mime_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                display_order INTEGER NOT NULL,
                FOREIGN KEY (session_id) REFERENCES journal_sessions(id),
                FOREIGN KEY (movement_id) REFERENCES asset_movements(id)
            );
            CREATE INDEX IF NOT EXISTS idx_journal_asset
                ON asset_movements(asset_id, occurred_at);
            CREATE INDEX IF NOT EXISTS idx_journal_media_session
                ON movement_media(session_id, display_order);
            """
        )


def _dict(row) -> dict[str, object] | None:
    return {key: row[key] for key in row.keys()} if row else None


def find_asset_by_plate(plate: str) -> dict[str, object] | None:
    with db_session() as conn:
        row = conn.execute(
            "SELECT id, external_identifier, plate, category, status, availability "
            "FROM fleet_assets WHERE UPPER(REPLACE(REPLACE(plate, ' ', ''), '-', '')) = ?",
            (plate,),
        ).fetchone()
    return _dict(row)


def create_session(values: dict[str, object]) -> dict[str, object]:
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO journal_sessions (
                id, token_hash, operation_type, asset_id, plate_snapshot,
                declared_driver_identifier, operational_shift, status,
                created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
            """,
            (
                values["id"], values["token_hash"], values["operation_type"],
                values["asset_id"], values["plate_snapshot"],
                values["declared_driver_identifier"],
                values.get("operational_shift"), values["created_at"],
                values["expires_at"],
            ),
        )
    return get_session(str(values["id"]))  # type: ignore[return-value]


def get_session(session_id: str) -> dict[str, object] | None:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM journal_sessions WHERE id = ?", (session_id,)
        ).fetchone()
    return _dict(row)


def create_media(values: dict[str, object]) -> dict[str, object]:
    with db_session() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(display_order), -1) + 1 "
            "FROM movement_media WHERE session_id = ?",
            (values["session_id"],),
        ).fetchone()
        order = int(row[0])
        conn.execute(
            """
            INSERT INTO movement_media (
                id, session_id, movement_id, media_type, phase, storage_key,
                verified_mime_type, size_bytes, sha256, display_order
            ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["id"], values["session_id"], values["media_type"],
                values["phase"], values["storage_key"],
                values["verified_mime_type"], values["size_bytes"],
                values["sha256"], order,
            ),
        )
    return get_session_media(str(values["session_id"]), str(values["id"]))  # type: ignore[return-value]


def get_session_media(session_id: str, media_id: str):
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM movement_media WHERE session_id = ? AND id = ?",
            (session_id, media_id),
        ).fetchone()
    return _dict(row)


def delete_media(session_id: str, media_id: str) -> None:
    with db_session() as conn:
        conn.execute(
            "DELETE FROM movement_media WHERE session_id = ? AND id = ? "
            "AND movement_id IS NULL",
            (session_id, media_id),
        )


def get_movement_by_submission(submission_id: str):
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM asset_movements WHERE client_submission_id = ?",
            (submission_id,),
        ).fetchone()
    return _dict(row)


def complete_session_atomic(
    session: dict[str, object],
    movement: dict[str, object],
    equipment: list[dict[str, object]],
) -> None:
    labels = {
        "telepass": "Telepass", "phone": "Telefono",
        "keys": "Chiavi", "fuel_card": "Carta carburante",
    }
    try:
        with db_session() as conn:
            cursor = conn.execute(
                "UPDATE journal_sessions SET status = 'completed', completed_at = ? "
                "WHERE id = ? AND status = 'open'",
                (movement["created_at"], session["id"]),
            )
            if getattr(cursor, "rowcount", 1) == 0:
                raise sqlite3.IntegrityError("Session already completed")
            conn.execute(
                """
                INSERT INTO asset_movements (
                    id, session_id, schema_version, organization_id,
                    operational_unit_id, asset_id, plate_snapshot,
                    declared_driver_identifier, operation_type,
                    operational_shift, occurred_at, timezone, odometer_km,
                    fuel_percentage, cleanliness_status, anomaly_present,
                    anomaly_description, operational_note,
                    client_submission_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    movement["id"], session["id"], movement["schema_version"],
                    movement["organization_id"], movement["operational_unit_id"],
                    session["asset_id"], session["plate_snapshot"],
                    session["declared_driver_identifier"],
                    session["operation_type"], session["operational_shift"],
                    movement["occurred_at"], movement["timezone"],
                    movement["odometer_km"], movement["fuel_percentage"],
                    movement["cleanliness_status"],
                    int(bool(movement["anomaly_present"])),
                    movement["anomaly_description"], movement["operational_note"],
                    movement["client_submission_id"], movement["created_at"],
                ),
            )
            for item in equipment:
                conn.execute(
                    "INSERT INTO movement_equipment VALUES (?, ?, ?, ?, ?)",
                    (
                        movement["id"], item["code"], labels[str(item["code"])],
                        item["status"], item.get("note"),
                    ),
                )
            conn.execute(
                "UPDATE movement_media SET movement_id = ? WHERE session_id = ?",
                (movement["id"], session["id"]),
            )
    except sqlite3.IntegrityError:
        raise


def receipt(movement_id: str) -> dict[str, object] | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT id, schema_version, plate_snapshot, operation_type,
                   occurred_at, odometer_km, fuel_percentage, cleanliness_status,
                   anomaly_present, created_at
            FROM asset_movements WHERE id = ?
            """,
            (movement_id,),
        ).fetchone()
        if not row:
            return None
        media = conn.execute(
            "SELECT id, media_type, verified_mime_type, size_bytes, sha256, display_order "
            "FROM movement_media WHERE movement_id = ? ORDER BY display_order",
            (movement_id,),
        ).fetchall()
    payload = _dict(row)
    payload["anomaly_present"] = bool(payload["anomaly_present"])
    payload["media"] = [_dict(item) for item in media]
    payload["verification_id"] = f"JM-{str(payload['id']).split('-')[0].upper()}"
    return payload
