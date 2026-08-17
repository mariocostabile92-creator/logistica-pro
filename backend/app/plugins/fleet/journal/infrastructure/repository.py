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
                organization_id TEXT,
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
                organization_id TEXT,
                vehicle_id INTEGER,
                original_filename TEXT,
                uploaded_at TEXT,
                evidence_type TEXT,
                evidence_slot TEXT,
                captured_at TEXT,
                received_at TEXT,
                capture_source TEXT,
                freshness_status TEXT,
                freshness_warning TEXT,
                reused_from_media_id TEXT,
                reuse_detected INTEGER NOT NULL DEFAULT 0,
                operational_date TEXT,
                declared_driver_identifier TEXT,
                replaced_media_id TEXT,
                checkpoint TEXT,
                evidence_mode TEXT,
                FOREIGN KEY (session_id) REFERENCES journal_sessions(id),
                FOREIGN KEY (movement_id) REFERENCES asset_movements(id)
            );
            CREATE TABLE IF NOT EXISTS journal_checkpoint_events (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                vehicle_id INTEGER NOT NULL,
                driver_identifier TEXT NOT NULL,
                checkpoint TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES journal_sessions(id)
            );
            CREATE INDEX IF NOT EXISTS idx_journal_asset
                ON asset_movements(asset_id, occurred_at);
            CREATE INDEX IF NOT EXISTS idx_journal_media_session
                ON movement_media(session_id, display_order);
            """
        )
        _ensure_session_columns(conn)
        _ensure_media_columns(conn)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_journal_session_org_date ON journal_sessions(organization_id, operational_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_journal_movement_org_date ON asset_movements(organization_id, occurred_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_journal_media_org ON movement_media(organization_id, vehicle_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_journal_media_hash ON movement_media(organization_id, sha256)")
        conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS uq_journal_media_active_slot
               ON movement_media(session_id, checkpoint, evidence_slot)
               WHERE movement_id IS NULL
                 AND checkpoint IS NOT NULL
                 AND evidence_slot IS NOT NULL"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_journal_checkpoint_events_session ON journal_checkpoint_events(session_id, created_at)")
        conn.execute(
            """
            UPDATE journal_sessions
            SET organization_id=(
                SELECT organization_id FROM fleet_assets
                WHERE fleet_assets.id=journal_sessions.asset_id
            )
            WHERE organization_id IS NULL OR organization_id='default'
            """
        )
        conn.execute(
            """
            UPDATE asset_movements
            SET organization_id=(
                SELECT organization_id FROM journal_sessions
                WHERE journal_sessions.id=asset_movements.session_id
            )
            WHERE organization_id IS NULL OR organization_id='default'
            """
        )
        conn.execute(
            """
            UPDATE movement_media
            SET organization_id=(
                    SELECT organization_id FROM journal_sessions
                    WHERE journal_sessions.id=movement_media.session_id
                ),
                vehicle_id=COALESCE(
                    vehicle_id,
                    (SELECT asset_id FROM journal_sessions
                     WHERE journal_sessions.id=movement_media.session_id)
                )
            WHERE organization_id IS NULL OR organization_id='default'
               OR vehicle_id IS NULL
            """
        )


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
        "organization_id": "TEXT",
        "evidence_policy_version": "TEXT",
        "check_in_mode": "TEXT",
        "check_out_mode": "TEXT",
        "check_in_started_at": "TEXT",
        "check_in_completed_at": "TEXT",
        "check_out_started_at": "TEXT",
        "check_out_completed_at": "TEXT",
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


def _ensure_media_columns(conn) -> None:
    columns = {
        "organization_id": "TEXT",
        "vehicle_id": "INTEGER",
        "original_filename": "TEXT",
        "uploaded_at": "TEXT",
        "evidence_type": "TEXT",
        "evidence_slot": "TEXT",
        "captured_at": "TEXT",
        "received_at": "TEXT",
        "capture_source": "TEXT",
        "freshness_status": "TEXT",
        "freshness_warning": "TEXT",
        "reused_from_media_id": "TEXT",
        "reuse_detected": "INTEGER NOT NULL DEFAULT 0",
        "operational_date": "TEXT",
        "declared_driver_identifier": "TEXT",
        "replaced_media_id": "TEXT",
        "checkpoint": "TEXT",
        "evidence_mode": "TEXT",
    }
    if SETTINGS.database_backend == "postgresql":
        for name, definition in columns.items():
            conn.execute(f"ALTER TABLE movement_media ADD COLUMN IF NOT EXISTS {name} {definition}")
        return
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(movement_media)").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE movement_media ADD COLUMN {name} {definition}")


def _dict(row) -> dict[str, object] | None:
    return {key: row[key] for key in row.keys()} if row else None


def find_asset_by_plate(
    plate: str,
    organization_id: str,
) -> dict[str, object] | None:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT id, external_identifier, plate, category, status, availability
            FROM fleet_assets
            WHERE plate IS NOT NULL AND organization_id = ?
            """
            ,
            (organization_id,),
        ).fetchall()
    for row in rows:
        normalized = normalize_plate(row["plate"])
        if normalized == plate:
            return _dict(row)
    return None


def list_assets_for_organization(organization_id: str) -> list[dict[str, object]]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT id, external_identifier, plate, category, status, availability
            FROM fleet_assets
            WHERE organization_id = ? AND plate IS NOT NULL
            ORDER BY plate ASC, id ASC
            """,
            (organization_id,),
        ).fetchall()
    return [_dict(row) for row in rows]


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
                , organization_id, evidence_policy_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                values.get("organization_id"),
                values.get("evidence_policy_version"),
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


def update_checkpoint(
    session_id: str,
    checkpoint: str,
    mode: str,
    event_type: str,
    occurred_at: str,
    actor: str,
) -> dict[str, object] | None:
    import uuid

    if checkpoint not in {"CHECK_IN", "CHECK_OUT"}:
        raise ValueError("Checkpoint non valido.")
    if event_type not in {
        "journal_check_in_started", "journal_check_in_completed",
        "journal_check_out_started", "journal_check_out_completed",
    }:
        raise ValueError("Evento checkpoint non valido.")
    prefix = checkpoint.casefold()
    timestamp_column = (
        f"{prefix}_completed_at" if event_type.endswith("_completed")
        else f"{prefix}_started_at"
    )
    mode_column = f"{prefix}_mode"
    with db_session() as conn:
        session = conn.execute(
            "SELECT * FROM journal_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not session:
            return None
        conn.execute(
            f"""UPDATE journal_sessions
                SET {mode_column} = COALESCE({mode_column}, ?),
                    {timestamp_column} = COALESCE({timestamp_column}, ?)
                WHERE id = ?""",
            (mode, occurred_at, session_id),
        )
        conn.execute(
            """INSERT INTO journal_checkpoint_events (
                   id, organization_id, session_id, vehicle_id,
                   driver_identifier, checkpoint, event_type, actor, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()), session["organization_id"] or "default",
                session_id, session["asset_id"],
                session["declared_driver_identifier"], checkpoint,
                event_type, actor, occurred_at,
            ),
        )
    return get_session(session_id)


def checkpoint_events(session_id: str) -> list[dict[str, object]]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM journal_checkpoint_events WHERE session_id = ? ORDER BY created_at, id",
            (session_id,),
        ).fetchall()
    return [_dict(row) for row in rows]  # type: ignore[misc]


def movement_history(asset_id: int) -> list[dict[str, object]]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT m.id, m.operation_type, m.occurred_at, m.odometer_km,
                   m.declared_driver_identifier, s.operational_date
            FROM asset_movements m
            JOIN journal_sessions s ON s.id = m.session_id
            WHERE m.asset_id = ?
            ORDER BY m.occurred_at DESC, m.created_at DESC
            """,
            (asset_id,),
        ).fetchall()
    return [_dict(row) for row in rows]  # type: ignore[misc]


def find_reused_media(
    organization_id: str,
    session_id: str,
    sha256: str,
    vehicle_id: int,
    declared_driver_identifier: str,
) -> dict[str, object] | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT mm.id, mm.session_id, mm.received_at, s.operational_date,
                   s.plate_snapshot, s.declared_driver_identifier
            FROM movement_media mm
            JOIN journal_sessions s ON s.id = mm.session_id
            WHERE mm.organization_id = ? AND mm.sha256 = ?
              AND mm.session_id <> ? AND mm.movement_id IS NOT NULL
              AND (mm.vehicle_id = ? OR s.declared_driver_identifier = ?)
            ORDER BY COALESCE(mm.received_at, mm.uploaded_at) DESC, mm.id DESC
            LIMIT 1
            """,
            (
                organization_id,
                sha256,
                session_id,
                vehicle_id,
                declared_driver_identifier,
            ),
        ).fetchone()
    return _dict(row)


def create_media(values: dict[str, object]) -> tuple[dict[str, object], dict[str, object] | None]:
    with db_session() as conn:
        replaced = conn.execute(
            """
            SELECT * FROM movement_media
            WHERE session_id = ? AND checkpoint = ?
              AND evidence_slot = ? AND movement_id IS NULL
            ORDER BY display_order DESC LIMIT 1
            """,
            (values["session_id"], values["checkpoint"], values["evidence_slot"]),
        ).fetchone()
        if replaced:
            conn.execute("DELETE FROM movement_media WHERE id = ?", (replaced["id"],))
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
                verified_mime_type, size_bytes, sha256, display_order,
                organization_id, vehicle_id, original_filename, uploaded_at
                , evidence_type, evidence_slot, captured_at, received_at,
                capture_source, freshness_status, freshness_warning,
                reused_from_media_id, reuse_detected, operational_date,
                declared_driver_identifier, replaced_media_id,
                checkpoint, evidence_mode
            ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                values.get("organization_id"),
                values.get("vehicle_id"),
                values.get("original_filename"),
                values.get("uploaded_at"),
                values.get("evidence_type"),
                values.get("evidence_slot"),
                values.get("captured_at"),
                values.get("received_at"),
                values.get("capture_source"),
                values.get("freshness_status"),
                values.get("freshness_warning"),
                values.get("reused_from_media_id"),
                int(bool(values.get("reuse_detected"))),
                values.get("operational_date"),
                values.get("declared_driver_identifier"),
                replaced["id"] if replaced else None,
                values.get("checkpoint"),
                values.get("evidence_mode"),
            ),
        )
    created = get_session_media(
        str(values["session_id"]),
        str(values["id"]),
    )
    assert created is not None
    return created, _dict(replaced)


def session_media(session_id: str) -> list[dict[str, object]]:
    with db_session() as conn:
        rows = conn.execute(
            """SELECT * FROM movement_media
               WHERE session_id = ? ORDER BY display_order, id""",
            (session_id,),
        ).fetchall()
    return [_dict(row) for row in rows]  # type: ignore[misc]


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


def delete_media_admin(media_id: str, organization_id: str) -> dict[str, object] | None:
    media = movement_media(media_id, organization_id)
    if not media:
        return None
    with db_session() as conn:
        conn.execute("DELETE FROM movement_media WHERE id=? AND organization_id=?", (media_id, organization_id))
    return media


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
            SET status = 'completed', lifecycle_status = 'completed', completed_at = ?,
                operational_date = ?
            WHERE id = ? AND status = 'open'
              AND (
                evidence_policy_version IS NULL OR evidence_policy_version <> '2.0'
                OR (check_in_completed_at IS NOT NULL AND check_out_completed_at IS NOT NULL)
              )
            """,
            (movement["created_at"], movement["operational_date"], session["id"]),
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
                   s.id AS session_id, s.warnings_json, s.source, s.evidence_policy_version,
                   s.check_in_mode, s.check_out_mode,
                   s.check_in_started_at, s.check_in_completed_at,
                   s.check_out_started_at, s.check_out_completed_at
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
                   sha256, display_order, evidence_type, evidence_slot,
                   captured_at, received_at, freshness_status,
                   freshness_warning, reuse_detected, operational_date,
                   checkpoint, evidence_mode
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


def asset_history(asset_id: int, organization_id: str | None = None) -> dict[str, object] | None:
    organization_clause = " AND asset_movements.organization_id = ?" if organization_id else ""
    movement_params: tuple[object, ...] = (asset_id, organization_id) if organization_id else (asset_id,)
    with db_session() as conn:
        asset_clause = " AND a.organization_id = ?" if organization_id else ""
        asset_params: tuple[object, ...] = (
            (asset_id, organization_id) if organization_id else (asset_id,)
        )
        asset = conn.execute(
            f"""
            SELECT a.id, a.external_identifier, a.plate, a.category,
                   a.status, a.availability, a.capabilities, a.notes,
                   a.created_at, a.updated_at,
                   m.vehicle_model, m.rental_company
            FROM fleet_assets a
            LEFT JOIN fleet_asset_metadata m ON m.asset_id = a.id
            WHERE a.id = ? {asset_clause}
            """,
            asset_params,
        ).fetchone()
        if not asset:
            return None
        movements = conn.execute(
            f"""
            SELECT asset_movements.id, asset_movements.plate_snapshot,
                   asset_movements.declared_driver_identifier,
                   asset_movements.operation_type, asset_movements.operational_shift,
                   asset_movements.occurred_at, asset_movements.timezone,
                   asset_movements.odometer_km, asset_movements.fuel_percentage,
                   asset_movements.cleanliness_status,
                   asset_movements.anomaly_present,
                   asset_movements.anomaly_description,
                   asset_movements.operational_note,
                   asset_movements.created_at, journal_sessions.operational_date,
                   (SELECT id FROM damage_cases dc
                    WHERE dc.source_movement_id = asset_movements.id) AS damage_case_id,
                   (SELECT case_number FROM damage_cases dc
                    WHERE dc.source_movement_id = asset_movements.id) AS damage_case_number,
                   (SELECT status FROM damage_cases dc
                    WHERE dc.source_movement_id = asset_movements.id) AS damage_case_status,
                   (SELECT severity FROM damage_cases dc
                    WHERE dc.source_movement_id = asset_movements.id) AS damage_case_severity
            FROM asset_movements
            JOIN journal_sessions ON journal_sessions.id = asset_movements.session_id
            WHERE asset_movements.asset_id = ? {organization_clause}
            ORDER BY asset_movements.occurred_at DESC, asset_movements.created_at DESC
            """,
            movement_params,
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
                       size_bytes, display_order, evidence_type, evidence_slot,
                       captured_at, received_at, freshness_status,
                       freshness_warning, reuse_detected, operational_date,
                       checkpoint, evidence_mode
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
                    f"/api/fleet/journal-control-room/media/{row['id']}"
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


def movement_media(media_id: str, organization_id: str | None = None) -> dict[str, object] | None:
    clause = " AND organization_id = ?" if organization_id else ""
    params: tuple[object, ...] = (media_id, organization_id) if organization_id else (media_id,)
    with db_session() as conn:
        row = conn.execute(
            f"""
            SELECT id, movement_id, media_type, storage_key,
                   verified_mime_type, size_bytes, original_filename,
                   organization_id, vehicle_id, session_id, evidence_type,
                   evidence_slot, checkpoint, evidence_mode,
                   captured_at, received_at, freshness_status,
                   freshness_warning, reuse_detected, operational_date
            FROM movement_media
            WHERE id = ? {clause}
            """,
            params,
        ).fetchone()
    return _dict(row)


def all_media_records() -> list[dict[str, object]]:
    with db_session() as conn:
        rows = conn.execute("SELECT * FROM movement_media").fetchall()
    return [_dict(row) for row in rows]  # type: ignore[misc]
