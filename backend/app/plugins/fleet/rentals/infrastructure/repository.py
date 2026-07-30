from app.core.database import db_session
from app.utils.date_utils import utc_now_iso


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS fleet_rentals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_id INTEGER,
                damage_case_id INTEGER,
                maintenance_id INTEGER,
                replacement_vehicle TEXT NOT NULL,
                rental_company TEXT NOT NULL,
                contract_number TEXT,
                start_date TEXT NOT NULL,
                expected_end_date TEXT NOT NULL,
                end_date TEXT,
                reason TEXT NOT NULL,
                status TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (vehicle_id) REFERENCES fleet_assets(id),
                FOREIGN KEY (damage_case_id) REFERENCES damage_cases(id),
                FOREIGN KEY (maintenance_id) REFERENCES fleet_maintenances(id)
            );
            CREATE INDEX IF NOT EXISTS idx_rentals_vehicle
                ON fleet_rentals(vehicle_id, start_date);
            CREATE INDEX IF NOT EXISTS idx_rentals_status
                ON fleet_rentals(status, expected_end_date);
            """
        )


def _dict(row):
    return {key: row[key] for key in row.keys()} if row else None


def _select() -> str:
    return """
        SELECT r.*, a.plate, a.external_identifier,
               a.category AS vehicle_model,
               d.case_number AS damage_case_number,
               m.maintenance_number
        FROM fleet_rentals r
        LEFT JOIN fleet_assets a ON a.id = r.vehicle_id
        LEFT JOIN damage_cases d ON d.id = r.damage_case_id
        LEFT JOIN fleet_maintenances m ON m.id = r.maintenance_id
    """


def get(rental_id: int):
    with db_session() as conn:
        row = conn.execute(f"{_select()} WHERE r.id = ?", (rental_id,)).fetchone()
    return _dict(row)


def list_all(vehicle_id: int | None = None):
    where = "WHERE r.vehicle_id = ?" if vehicle_id else ""
    params = (vehicle_id,) if vehicle_id else ()
    with db_session() as conn:
        rows = conn.execute(
            f"""
            {_select()} {where}
            ORDER BY
              CASE r.status
                WHEN 'attivo' THEN 0 WHEN 'prorogato' THEN 1
                WHEN 'programmato' THEN 2 ELSE 3
              END,
              r.start_date DESC, r.id DESC
            """,
            params,
        ).fetchall()
    return [_dict(row) for row in rows]


def context(vehicle_id=None, damage_case_id=None, maintenance_id=None):
    with db_session() as conn:
        if maintenance_id:
            row = conn.execute(
                "SELECT vehicle_id FROM fleet_maintenances WHERE id = ?",
                (maintenance_id,),
            ).fetchone()
        elif damage_case_id:
            row = conn.execute(
                "SELECT vehicle_id FROM damage_cases WHERE id = ?",
                (damage_case_id,),
            ).fetchone()
        elif vehicle_id:
            row = conn.execute(
                "SELECT id AS vehicle_id FROM fleet_assets WHERE id = ?",
                (vehicle_id,),
            ).fetchone()
        else:
            return {"vehicle_id": None}
    return _dict(row)


def create(values):
    now = utc_now_iso()
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO fleet_rentals (
                vehicle_id, damage_case_id, maintenance_id, replacement_vehicle,
                rental_company, contract_number, start_date, expected_end_date,
                end_date, reason, status, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values.get("vehicle_id"), values.get("damage_case_id"),
                values.get("maintenance_id"), values["replacement_vehicle"],
                values["rental_company"], values.get("contract_number"),
                values["start_date"], values["expected_end_date"],
                values.get("end_date"), values["reason"], values["status"],
                values.get("notes"), now, now,
            ),
        )
        rental_id = int(cursor.lastrowid)
    return get(rental_id)


def update(rental_id: int, changes):
    allowed = {
        "replacement_vehicle", "rental_company", "contract_number",
        "start_date", "expected_end_date", "end_date", "reason", "status", "notes",
    }
    values = {key: value for key, value in changes.items() if key in allowed}
    if not values:
        return get(rental_id)
    values["updated_at"] = utc_now_iso()
    with db_session() as conn:
        assignments = ", ".join(f"{key} = ?" for key in values)
        cursor = conn.execute(
            f"UPDATE fleet_rentals SET {assignments} WHERE id = ?",
            [*values.values(), rental_id],
        )
        if cursor.rowcount == 0:
            return None
    return get(rental_id)
