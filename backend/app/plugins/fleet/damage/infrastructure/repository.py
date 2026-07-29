from app.core.database import db_session
from app.utils.date_utils import utc_now_iso


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS damage_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_number TEXT UNIQUE,
                vehicle_id INTEGER NOT NULL,
                source_movement_id TEXT,
                source_document_id TEXT,
                declared_driver TEXT,
                occurred_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                closed_at TEXT,
                origin TEXT NOT NULL,
                manual_reason TEXT,
                description TEXT NOT NULL,
                severity TEXT NOT NULL,
                status TEXT NOT NULL,
                vehicle_operational_status TEXT NOT NULL,
                repair_shop TEXT,
                estimated_cost TEXT,
                final_cost TEXT,
                expected_deductible TEXT,
                applied_deductible TEXT,
                FOREIGN KEY (vehicle_id) REFERENCES fleet_assets(id),
                FOREIGN KEY (source_movement_id) REFERENCES asset_movements(id),
                UNIQUE (source_movement_id)
            );
            CREATE TABLE IF NOT EXISTS damage_case_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                damage_case_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                previous_status TEXT,
                new_status TEXT,
                note TEXT,
                created_at TEXT NOT NULL,
                actor TEXT NOT NULL,
                FOREIGN KEY (damage_case_id) REFERENCES damage_cases(id)
            );
            CREATE INDEX IF NOT EXISTS idx_damage_vehicle
                ON damage_cases(vehicle_id, occurred_at);
            CREATE INDEX IF NOT EXISTS idx_damage_status
                ON damage_cases(status, severity);
            CREATE INDEX IF NOT EXISTS idx_damage_events
                ON damage_case_events(damage_case_id, created_at);
            """
        )


def _dict(row):
    return {key: row[key] for key in row.keys()} if row else None


def get_case(case_id: int):
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT c.*, a.plate, a.external_identifier, a.category AS vehicle_model,
                   a.availability AS asset_availability
            FROM damage_cases c
            JOIN fleet_assets a ON a.id = c.vehicle_id
            WHERE c.id = ?
            """,
            (case_id,),
        ).fetchone()
    return _dict(row)


def get_by_movement(movement_id: str):
    with db_session() as conn:
        row = conn.execute(
            "SELECT id FROM damage_cases WHERE source_movement_id = ?",
            (movement_id,),
        ).fetchone()
    return get_case(int(row["id"])) if row else None


def create_case(values: dict[str, object], actor: str):
    now = utc_now_iso()
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO damage_cases (
                case_number, vehicle_id, source_movement_id, source_document_id,
                declared_driver, occurred_at, created_at, updated_at, origin,
                manual_reason, description, severity, status,
                vehicle_operational_status, repair_shop, estimated_cost, final_cost
            ) VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'nuova', ?, ?, ?, ?)
            """,
            (
                values["vehicle_id"], values.get("source_movement_id"),
                values.get("source_document_id"), values.get("declared_driver"),
                values["occurred_at"], now, now, values["origin"],
                values.get("manual_reason"), values["description"],
                values["severity"], values["vehicle_operational_status"],
                values.get("repair_shop"), values.get("estimated_cost"),
                values.get("final_cost"),
            ),
        )
        case_id = int(cursor.lastrowid)
        case_number = f"DMG-{now[:4]}-{case_id:06d}"
        conn.execute(
            "UPDATE damage_cases SET case_number = ? WHERE id = ?",
            (case_number, case_id),
        )
        conn.execute(
            """
            INSERT INTO damage_case_events
                (damage_case_id, event_type, previous_status, new_status, note, created_at, actor)
            VALUES (?, 'pratica_creata', NULL, 'nuova', ?, ?, ?)
            """,
            (case_id, values.get("manual_reason") or "Pratica creata", now, actor),
        )
    return get_case(case_id)


def list_cases(filters: dict[str, object]):
    clauses = []
    parameters: list[object] = []
    for field in ("status", "severity", "vehicle_operational_status"):
        value = filters.get(field)
        if value:
            clauses.append(f"c.{field} = ?")
            parameters.append(value)
    if filters.get("plate"):
        clauses.append("UPPER(a.plate) LIKE ?")
        parameters.append(f"%{str(filters['plate']).upper()}%")
    if filters.get("driver"):
        clauses.append("LOWER(c.declared_driver) LIKE ?")
        parameters.append(f"%{str(filters['driver']).lower()}%")
    if filters.get("date_from"):
        clauses.append("c.occurred_at >= ?")
        parameters.append(filters["date_from"])
    if filters.get("date_to"):
        clauses.append("c.occurred_at <= ?")
        parameters.append(f"{filters['date_to']}T23:59:59")
    if filters.get("search"):
        term = f"%{str(filters['search']).lower()}%"
        clauses.append(
            "(LOWER(c.case_number) LIKE ? OR LOWER(COALESCE(a.plate,'')) LIKE ? "
            "OR LOWER(COALESCE(c.declared_driver,'')) LIKE ? OR "
            "LOWER(c.description) LIKE ? OR LOWER(COALESCE(c.repair_shop,'')) LIKE ?)"
        )
        parameters.extend([term] * 5)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with db_session() as conn:
        rows = conn.execute(
            f"""
            SELECT c.*, a.plate, a.external_identifier, a.category AS vehicle_model,
                   a.availability AS asset_availability
            FROM damage_cases c JOIN fleet_assets a ON a.id = c.vehicle_id
            {where}
            ORDER BY
              CASE WHEN c.vehicle_operational_status IN ('fermo','in_officina') THEN 0 ELSE 1 END,
              CASE c.severity WHEN 'critica' THEN 0 WHEN 'alta' THEN 1 WHEN 'media' THEN 2 ELSE 3 END,
              c.occurred_at DESC
            """,
            parameters,
        ).fetchall()
    return [_dict(row) for row in rows]


def update_case(case_id: int, changes: dict[str, object], actor: str):
    current = get_case(case_id)
    if not current:
        return None
    allowed = (
        "description", "severity", "vehicle_operational_status",
        "repair_shop", "estimated_cost", "final_cost",
    )
    effective = {key: value for key, value in changes.items() if key in allowed}
    if not effective:
        return current
    now = utc_now_iso()
    with db_session() as conn:
        assignments = ", ".join(f"{key} = ?" for key in effective)
        conn.execute(
            f"UPDATE damage_cases SET {assignments}, updated_at = ? WHERE id = ?",
            [*effective.values(), now, case_id],
        )
        for key, event_type in (
            ("severity", "gravita_modificata"),
            ("repair_shop", "officina_assegnata"),
            ("estimated_cost", "preventivo_registrato"),
            ("final_cost", "preventivo_registrato"),
            ("description", "nota_aggiunta"),
        ):
            if key in effective and effective[key] != current.get(key):
                conn.execute(
                    """
                    INSERT INTO damage_case_events
                        (damage_case_id, event_type, note, created_at, actor)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (case_id, event_type, f"{key}: {effective[key]}", now, actor),
                )
        if (
            "vehicle_operational_status" in effective
            and effective["vehicle_operational_status"] != current["vehicle_operational_status"]
        ):
            event_type = (
                "veicolo_fermato"
                if effective["vehicle_operational_status"] in ("fermo", "in_officina")
                else "veicolo_ripristinato"
            )
            conn.execute(
                """
                INSERT INTO damage_case_events
                    (damage_case_id, event_type, note, created_at, actor)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    case_id, event_type,
                    f"Stato mezzo: {current['vehicle_operational_status']} → "
                    f"{effective['vehicle_operational_status']}",
                    now, actor,
                ),
            )
    return get_case(case_id)


def change_status(case_id: int, status: str, note: str, actor: str):
    current = get_case(case_id)
    if not current:
        return None
    now = utc_now_iso()
    closed_at = now if status == "chiusa" else None
    event_type = (
        "pratica_riaperta" if current["status"] == "chiusa"
        else "pratica_chiusa" if status == "chiusa"
        else "pratica_annullata" if status == "annullata"
        else "stato_modificato"
    )
    with db_session() as conn:
        conn.execute(
            "UPDATE damage_cases SET status = ?, updated_at = ?, closed_at = ? WHERE id = ?",
            (status, now, closed_at, case_id),
        )
        conn.execute(
            """
            INSERT INTO damage_case_events
                (damage_case_id, event_type, previous_status, new_status, note, created_at, actor)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (case_id, event_type, current["status"], status, note, now, actor),
        )
    return get_case(case_id)


def add_note(case_id: int, note: str, actor: str):
    if not get_case(case_id):
        return None
    now = utc_now_iso()
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO damage_case_events
                (damage_case_id, event_type, note, created_at, actor)
            VALUES (?, 'nota_aggiunta', ?, ?, ?)
            """,
            (case_id, note, now, actor),
        )
        conn.execute(
            "UPDATE damage_cases SET updated_at = ? WHERE id = ?",
            (now, case_id),
        )
    return list_events(case_id)


def list_events(case_id: int):
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM damage_case_events WHERE damage_case_id = ? ORDER BY created_at, id",
            (case_id,),
        ).fetchall()
    return [_dict(row) for row in rows]


def open_case_operational_states(vehicle_id: int, excluding_case_id: int | None = None):
    parameters: list[object] = [vehicle_id]
    exclusion = ""
    if excluding_case_id is not None:
        exclusion = "AND id != ?"
        parameters.append(excluding_case_id)
    with db_session() as conn:
        rows = conn.execute(
            f"""
            SELECT vehicle_operational_status
            FROM damage_cases
            WHERE vehicle_id = ? AND status NOT IN ('chiusa', 'annullata') {exclusion}
            """,
            parameters,
        ).fetchall()
    return [str(row["vehicle_operational_status"]) for row in rows]


def record_operational_status(
    case_id: int,
    previous: str,
    current: str,
    reason: str,
    actor: str,
    origin: str,
):
    now = utc_now_iso()
    with db_session() as conn:
        conn.execute(
            """
            UPDATE damage_cases
            SET vehicle_operational_status = ?, updated_at = ?
            WHERE id = ?
            """,
            (current, now, case_id),
        )
        conn.execute(
            """
            INSERT INTO damage_case_events
                (damage_case_id, event_type, previous_status, new_status,
                 note, created_at, actor)
            VALUES (?, 'stato_operativo_mezzo_modificato', ?, ?, ?, ?, ?)
            """,
            (case_id, previous, current, f"{origin}. {reason}", now, actor),
        )


def candidates():
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT m.id AS movement_id, m.asset_id AS vehicle_id, m.plate_snapshot AS plate,
                   a.external_identifier, a.category AS vehicle_model, a.availability,
                   m.declared_driver_identifier AS declared_driver, m.occurred_at,
                   m.anomaly_description AS description,
                   (SELECT COUNT(*) FROM movement_media mm
                    WHERE mm.movement_id = m.id AND mm.media_type = 'image') AS photo_count
            FROM asset_movements m
            JOIN fleet_assets a ON a.id = m.asset_id
            LEFT JOIN damage_cases c ON c.source_movement_id = m.id
            WHERE m.anomaly_present = 1 AND c.id IS NULL
            ORDER BY m.occurred_at DESC
            """
        ).fetchall()
    return [_dict(row) for row in rows]
