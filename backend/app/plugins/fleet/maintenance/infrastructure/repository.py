from app.auth.tenant_context import current_organization_id
from app.core.database import db_session
from app.utils.date_utils import utc_now_iso


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS fleet_maintenances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                maintenance_number TEXT UNIQUE,
                vehicle_id INTEGER NOT NULL,
                damage_case_id INTEGER,
                description TEXT NOT NULL,
                maintenance_type TEXT NOT NULL,
                status TEXT NOT NULL,
                priority TEXT NOT NULL,
                repair_shop TEXT,
                opened_at TEXT NOT NULL,
                expected_at TEXT,
                completed_at TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (vehicle_id) REFERENCES fleet_assets(id),
                FOREIGN KEY (damage_case_id) REFERENCES damage_cases(id),
                UNIQUE (damage_case_id)
            );
            CREATE TABLE IF NOT EXISTS fleet_maintenance_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                maintenance_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                previous_status TEXT,
                new_status TEXT,
                note TEXT,
                actor TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (maintenance_id) REFERENCES fleet_maintenances(id)
            );
            CREATE INDEX IF NOT EXISTS idx_maintenance_vehicle
                ON fleet_maintenances(vehicle_id, opened_at);
            CREATE INDEX IF NOT EXISTS idx_maintenance_status
                ON fleet_maintenances(status, priority);
            """
        )


def _dict(row):
    return {key: row[key] for key in row.keys()} if row else None


def _select() -> str:
    return """
        SELECT m.*, a.plate, a.external_identifier,
               a.category AS vehicle_model, d.case_number AS damage_case_number,
               (SELECT COUNT(*) FROM attachments att
                WHERE att.entity_type='maintenance' AND att.entity_id=m.id
                  AND att.organization_id=a.organization_id) AS attachment_count
        FROM fleet_maintenances m
        JOIN fleet_assets a ON a.id = m.vehicle_id
        LEFT JOIN damage_cases d ON d.id = m.damage_case_id
    """


def get(maintenance_id: int):
    organization_id = current_organization_id()
    with db_session() as conn:
        row = conn.execute(
            f"{_select()} WHERE m.id = ? AND a.organization_id = ?",
            (maintenance_id, organization_id),
        ).fetchone()
    return _dict(row)


def get_by_damage_case(damage_case_id: int):
    organization_id = current_organization_id()
    with db_session() as conn:
        row = conn.execute(
            f"{_select()} WHERE m.damage_case_id = ? AND a.organization_id = ?",
            (damage_case_id, organization_id),
        ).fetchone()
    return _dict(row)


def list_all(vehicle_id: int | None = None):
    clauses = ["a.organization_id = ?"]
    params: list[object] = [current_organization_id()]
    if vehicle_id:
        clauses.append("m.vehicle_id = ?")
        params.append(vehicle_id)
    where = f"WHERE {' AND '.join(clauses)}"
    with db_session() as conn:
        rows = conn.execute(
            f"""
            {_select()} {where}
            ORDER BY
              CASE m.status
                WHEN 'in_lavorazione' THEN 0
                WHEN 'aperta' THEN 1
                WHEN 'programmata' THEN 2
                ELSE 3
              END,
              CASE m.priority
                WHEN 'critica' THEN 0
                WHEN 'alta' THEN 1
                WHEN 'media' THEN 2
                ELSE 3
              END,
              m.opened_at DESC
            """,
            params,
        ).fetchall()
    return [_dict(row) for row in rows]


def list_events(maintenance_id: int):
    organization_id = current_organization_id()
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT e.* FROM fleet_maintenance_events e
            JOIN fleet_maintenances m ON m.id=e.maintenance_id
            JOIN fleet_assets a ON a.id=m.vehicle_id
            WHERE e.maintenance_id = ? AND a.organization_id = ?
            ORDER BY e.created_at ASC, e.id ASC
            """,
            (maintenance_id, organization_id),
        ).fetchall()
    return [_dict(row) for row in rows]


def create(values: dict[str, object], actor: str):
    now = utc_now_iso()
    organization_id = current_organization_id()
    with db_session() as conn:
        owned = conn.execute(
            "SELECT 1 FROM fleet_assets WHERE id=? AND organization_id=?",
            (values["vehicle_id"], organization_id),
        ).fetchone()
        if not owned:
            return None
        damage_case_id = values.get("damage_case_id")
        if damage_case_id and not conn.execute(
            """
            SELECT 1 FROM damage_cases d
            JOIN fleet_assets a ON a.id=d.vehicle_id
            WHERE d.id=? AND a.organization_id=?
            """,
            (damage_case_id, organization_id),
        ).fetchone():
            return None
        cursor = conn.execute(
            """
            INSERT INTO fleet_maintenances (
                maintenance_number, vehicle_id, damage_case_id, description,
                maintenance_type, status, priority, repair_shop, opened_at,
                expected_at, notes, created_at, updated_at
            ) VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["vehicle_id"], values.get("damage_case_id"),
                values["description"], values["maintenance_type"],
                values.get("status", "aperta"), values.get("priority", "media"),
                values.get("repair_shop"), values.get("opened_at") or now,
                values.get("expected_at"), values.get("notes"), now, now,
            ),
        )
        maintenance_id = int(cursor.lastrowid)
        number = f"MNT-{now[:4]}-{maintenance_id:06d}"
        conn.execute(
            "UPDATE fleet_maintenances SET maintenance_number = ? WHERE id = ?",
            (number, maintenance_id),
        )
        conn.execute(
            """
            INSERT INTO fleet_maintenance_events (
                maintenance_id, event_type, new_status, note, actor, created_at
            ) VALUES (?, 'manutenzione_creata', ?, ?, ?, ?)
            """,
            (
                maintenance_id, values.get("status", "aperta"),
                values.get("notes") or "Manutenzione aperta", actor, now,
            ),
        )
    return get(maintenance_id)


def update(maintenance_id: int, changes: dict[str, object], actor: str):
    current = get(maintenance_id)
    if not current:
        return None
    allowed = {
        "description", "maintenance_type", "status", "priority",
        "repair_shop", "expected_at", "notes",
    }
    effective = {
        key: value for key, value in changes.items()
        if key in allowed and value != current.get(key)
    }
    if not effective:
        return current
    now = utc_now_iso()
    if effective.get("status") == "completata":
        effective["completed_at"] = now
    elif "status" in effective:
        effective["completed_at"] = None
    with db_session() as conn:
        assignments = ", ".join(f"{key} = ?" for key in effective)
        conn.execute(
            f"UPDATE fleet_maintenances SET {assignments}, updated_at = ? WHERE id = ?",
            [*effective.values(), now, maintenance_id],
        )
        conn.execute(
            """
            INSERT INTO fleet_maintenance_events (
                maintenance_id, event_type, previous_status, new_status,
                note, actor, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                maintenance_id,
                "stato_modificato" if "status" in effective else "dettaglio_aggiornato",
                current["status"],
                effective.get("status", current["status"]),
                changes.get("notes") or "Manutenzione aggiornata",
                actor,
                now,
            ),
        )
    return get(maintenance_id)
