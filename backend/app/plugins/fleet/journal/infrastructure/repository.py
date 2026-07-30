import sqlite3

from app.core.config import SETTINGS
from app.core.database import db_session
from app.utils.text_normalizer import normalize_plate


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
        _ensure_session_columns(conn)


def _ensure_session_columns(conn) -> None:
    columns = {
        "source": "TEXT NOT NULL DEFAULT 'driver'",
        "lifecycle_status": "TEXT NOT NULL DEFAULT 'in_progress'",
        "scheduled_at": "TEXT",
        "opened_at": "TEXT",
        "in_progress_at": "TEXT",
        "driver_name": "TEXT",
        "driver_surname": "TEXT",
        "warnings_json": "TEXT NOT NULL DEFAULT '[]'",
        "operational_date": "TEXT",
    }
    if SETTINGS.database_backend == "postgresql":
        for name, definition in columns.items():
            conn.execute(
                f"ALTER TABLE journal_sessions ADD COLUMN IF NOT EXISTS {name} {definition}"
            )
        return
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(journal_sessions)").fetchall()
    }
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE journal_sessions ADD COLUMN {name} {definition}")


def _dict(row) -> dict[str, object] | None:
    return {key: row[key] for key in row.keys()} if row else None


def find_asset_by_plate(plate: str) -> dict[str, object] | None:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT id, external_identifier, plate, category, status, availability
            FROM fleet_assets
            WHERE plate IS NOT NULL
            """
        ).fetchall()
    for row in rows:
        normalized = normalize_plate(row["plate"])
        if normalized == plate:
            return _dict(row)
    return None


def create_session(values: dict[str, object]) -> dict[str, object]:
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO journal_sessions (
                id, token_hash, operation_type, asset_id, plate_snapshot,
                declared_driver_identifier, operational_shift, status,
                created_at, expires_at, source, lifecycle_status,
                scheduled_at, opened_at, in_progress_at, driver_name,
                driver_surname, warnings_json, operational_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["id"],
                values["token_hash"],
                values["operation_type"],
                values["asset_id"],
                values["plate_snapshot"],
                values["declared_driver_identifier"],
                values.get("operational_shift"),
                values["created_at"],
                values["expires_at"],
                values.get("source", "driver"),
                values.get("lifecycle_status", "in_progress"),
                values.get("scheduled_at"),
                values.get("opened_at"),
                values.get("in_progress_at"),
                values.get("driver_name"),
                values.get("driver_surname"),
                values.get("warnings_json", "[]"),
                values.get("operational_date"),
            ),
        )
    return get_session(str(values["id"]))  # type: ignore[return-value]


def get_session(session_id: str) -> dict[str, object] | None:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM journal_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    return _dict(row)


def transition_session(
    session_id: str,
    from_statuses: tuple[str, ...],
    to_status: str,
    timestamp_column: str,
    occurred_at: str,
) -> dict[str, object] | None:
    allowed_columns = {"opened_at", "in_progress_at"}
    if timestamp_column not in allowed_columns:
        raise ValueError("Colonna evento sessione non valida.")
    placeholders = ",".join("?" for _ in from_statuses)
    with db_session() as conn:
        conn.execute(
            f"""
            UPDATE journal_sessions
            SET lifecycle_status = ?, {timestamp_column} = COALESCE({timestamp_column}, ?)
            WHERE id = ? AND lifecycle_status IN ({placeholders})
            """,
            (to_status, occurred_at, session_id, *from_statuses),
        )
    return get_session(session_id)


def update_session_warnings(
    session_id: str,
    warnings_json: str,
) -> dict[str, object] | None:
    with db_session() as conn:
        conn.execute(
            "UPDATE journal_sessions SET warnings_json = ? WHERE id = ?",
            (warnings_json, session_id),
        )
    return get_session(session_id)


def movement_history(asset_id: int) -> list[dict[str, object]]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT id, operation_type, occurred_at, odometer_km,
                   declared_driver_identifier
            FROM asset_movements
            WHERE asset_id = ?
            ORDER BY occurred_at DESC, created_at DESC
            """,
            (asset_id,),
        ).fetchall()
    return [_dict(row) for row in rows]  # type: ignore[misc]


def create_media(values: dict[str, object]) -> dict[str, object]:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(MAX(display_order), -1) + 1
            FROM movement_media
            WHERE session_id = ?
            """,
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
                values["id"],
                values["session_id"],
                values["media_type"],
                values["phase"],
                values["storage_key"],
                values["verified_mime_type"],
                values["size_bytes"],
                values["sha256"],
                order,
            ),
        )
    return get_session_media(
        str(values["session_id"]),
        str(values["id"]),
    )  # type: ignore[return-value]


def get_session_media(
    session_id: str,
    media_id: str,
) -> dict[str, object] | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM movement_media
            WHERE session_id = ? AND id = ?
            """,
            (session_id, media_id),
        ).fetchone()
    return _dict(row)


def delete_media(session_id: str, media_id: str) -> None:
    with db_session() as conn:
        conn.execute(
            """
            DELETE FROM movement_media
            WHERE session_id = ? AND id = ? AND movement_id IS NULL
            """,
            (session_id, media_id),
        )


def get_movement_by_submission(
    submission_id: str,
) -> dict[str, object] | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM asset_movements
            WHERE client_submission_id = ?
            """,
            (submission_id,),
        ).fetchone()
    return _dict(row)


def complete_session_atomic(
    session: dict[str, object],
    movement: dict[str, object],
    equipment: list[dict[str, object]],
) -> None:
    labels = {
        "telepass": "Telepass",
        "phone": "Telefono",
        "keys": "Chiavi",
        "fuel_card": "Carta carburante",
    }
    with db_session() as conn:
        cursor = conn.execute(
            """
            UPDATE journal_sessions
            SET status = 'completed', lifecycle_status = 'completed', completed_at = ?
            WHERE id = ? AND status = 'open'
            """,
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
                movement["id"],
                session["id"],
                movement["schema_version"],
                movement["organization_id"],
                movement["operational_unit_id"],
                session["asset_id"],
                session["plate_snapshot"],
                session["declared_driver_identifier"],
                session["operation_type"],
                session["operational_shift"],
                movement["occurred_at"],
                movement["timezone"],
                movement["odometer_km"],
                movement["fuel_percentage"],
                movement["cleanliness_status"],
                int(bool(movement["anomaly_present"])),
                movement["anomaly_description"],
                movement["operational_note"],
                movement["client_submission_id"],
                movement["created_at"],
            ),
        )
        for item in equipment:
            conn.execute(
                """
                INSERT INTO movement_equipment
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    movement["id"],
                    item["code"],
                    labels[str(item["code"])],
                    item["status"],
                    item.get("note"),
                ),
            )
        conn.execute(
            """
            UPDATE movement_media
            SET movement_id = ?
            WHERE session_id = ?
            """,
            (movement["id"], session["id"]),
        )


def receipt(movement_id: str) -> dict[str, object] | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT m.id, m.schema_version, m.plate_snapshot, m.operation_type,
                   occurred_at, odometer_km, fuel_percentage,
                   cleanliness_status, anomaly_present, m.created_at,
                   s.warnings_json, s.source
            FROM asset_movements m
            JOIN journal_sessions s ON s.id = m.session_id
            WHERE m.id = ?
            """,
            (movement_id,),
        ).fetchone()
        if not row:
            return None
        media = conn.execute(
            """
            SELECT id, media_type, verified_mime_type, size_bytes,
                   sha256, display_order
            FROM movement_media
            WHERE movement_id = ?
            ORDER BY display_order
            """,
            (movement_id,),
        ).fetchall()
    payload = _dict(row)
    assert payload is not None
    payload["anomaly_present"] = bool(payload["anomaly_present"])
    payload["media"] = [_dict(item) for item in media]
    payload["verification_id"] = (
        f"JM-{str(payload['id']).split('-')[0].upper()}"
    )
    return payload


def asset_history(asset_id: int) -> dict[str, object] | None:
    with db_session() as conn:
        asset = conn.execute(
            """
            SELECT a.id, a.external_identifier, a.plate, a.category,
                   a.status, a.availability, a.capabilities, a.notes,
                   a.created_at, a.updated_at,
                   m.vehicle_model, m.rental_company
            FROM fleet_assets a
            LEFT JOIN fleet_asset_metadata m ON m.asset_id = a.id
            WHERE a.id = ?
            """,
            (asset_id,),
        ).fetchone()
        if not asset:
            return None
        movements = conn.execute(
            """
            SELECT id, plate_snapshot, declared_driver_identifier,
                   operation_type, operational_shift, occurred_at, timezone,
                   odometer_km, fuel_percentage, cleanliness_status,
                   anomaly_present, anomaly_description, operational_note,
                   created_at,
                   (SELECT id FROM damage_cases dc
                    WHERE dc.source_movement_id = asset_movements.id) AS damage_case_id,
                   (SELECT case_number FROM damage_cases dc
                    WHERE dc.source_movement_id = asset_movements.id) AS damage_case_number,
                   (SELECT status FROM damage_cases dc
                    WHERE dc.source_movement_id = asset_movements.id) AS damage_case_status,
                   (SELECT severity FROM damage_cases dc
                    WHERE dc.source_movement_id = asset_movements.id) AS damage_case_severity
            FROM asset_movements
            WHERE asset_id = ?
            ORDER BY occurred_at DESC, created_at DESC
            """,
            (asset_id,),
        ).fetchall()
        movement_ids = [row["id"] for row in movements]
        equipment_by_movement: dict[str, list[dict[str, object]]] = {
            movement_id: [] for movement_id in movement_ids
        }
        media_by_movement: dict[str, list[dict[str, object]]] = {
            movement_id: [] for movement_id in movement_ids
        }
        if movement_ids:
            placeholders = ",".join("?" for _ in movement_ids)
            equipment = conn.execute(
                f"""
                SELECT movement_id, equipment_code, equipment_label_snapshot,
                       equipment_status, note
                FROM movement_equipment
                WHERE movement_id IN ({placeholders})
                ORDER BY movement_id, equipment_label_snapshot
                """,
                movement_ids,
            ).fetchall()
            media = conn.execute(
                f"""
                SELECT id, movement_id, media_type, verified_mime_type,
                       size_bytes, display_order
                FROM movement_media
                WHERE movement_id IN ({placeholders})
                ORDER BY movement_id, display_order
                """,
                movement_ids,
            ).fetchall()
            for row in equipment:
                equipment_by_movement[row["movement_id"]].append(_dict(row))
            for row in media:
                item = _dict(row)
                assert item is not None
                item["url"] = (
                    f"/api/plugins/fleet/v1/journal/media/{row['id']}"
                )
                media_by_movement[row["movement_id"]].append(item)

    asset_payload = _dict(asset)
    assert asset_payload is not None
    history = []
    for row in movements:
        item = _dict(row)
        assert item is not None
        item["anomaly_present"] = bool(item["anomaly_present"])
        item["equipment"] = equipment_by_movement[str(item["id"])]
        item["media"] = media_by_movement[str(item["id"])]
        history.append(item)
    return {"asset": asset_payload, "movements": history}


def movement_media(media_id: str) -> dict[str, object] | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT id, movement_id, media_type, storage_key,
                   verified_mime_type, size_bytes
            FROM movement_media
            WHERE id = ? AND movement_id IS NOT NULL
            """,
            (media_id,),
        ).fetchone()
    return _dict(row)
