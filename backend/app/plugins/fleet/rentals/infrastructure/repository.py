from app.auth.tenant_context import current_organization_id
from app.core.database import db_session
from app.core.tenant_schema import ensure_column
from app.utils.date_utils import utc_now_iso


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS fleet_rentals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id TEXT,
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
        ensure_column(conn, "fleet_rentals", "organization_id", "TEXT")
        owner = conn.execute(
            "SELECT id FROM organizations ORDER BY created_at ASC, id ASC LIMIT 1"
        ).fetchone()
        if owner:
            conn.execute(
                """
                UPDATE fleet_rentals
                SET organization_id = COALESCE(
                    (SELECT organization_id FROM fleet_assets
                     WHERE fleet_assets.id=fleet_rentals.vehicle_id),
                    ?
                )
                WHERE organization_id IS NULL OR organization_id='default'
                """,
                (owner["id"],),
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_rentals_organization "
            "ON fleet_rentals(organization_id, status)"
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
    organization_id = current_organization_id()
    with db_session() as conn:
        row = conn.execute(
            f"{_select()} WHERE r.id = ? AND r.organization_id = ?",
            (rental_id, organization_id),
        ).fetchone()
    return _dict(row)


def list_all(vehicle_id: int | None = None):
    clauses = ["r.organization_id = ?"]
    params: list[object] = [current_organization_id()]
    if vehicle_id:
        clauses.append("r.vehicle_id = ?")
        params.append(vehicle_id)
    where = f"WHERE {' AND '.join(clauses)}"
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
    organization_id = current_organization_id()
    with db_session() as conn:
        if maintenance_id:
            row = conn.execute(
                """
                SELECT m.vehicle_id FROM fleet_maintenances m
                JOIN fleet_assets a ON a.id=m.vehicle_id
                WHERE m.id = ? AND a.organization_id = ?
                """,
                (maintenance_id, organization_id),
            ).fetchone()
        elif damage_case_id:
            row = conn.execute(
                """
                SELECT d.vehicle_id FROM damage_cases d
                JOIN fleet_assets a ON a.id=d.vehicle_id
                WHERE d.id = ? AND a.organization_id = ?
                """,
                (damage_case_id, organization_id),
            ).fetchone()
        elif vehicle_id:
            row = conn.execute(
                """
                SELECT id AS vehicle_id FROM fleet_assets
                WHERE id = ? AND organization_id = ?
                """,
                (vehicle_id, organization_id),
            ).fetchone()
        else:
            return {"vehicle_id": None}
    return _dict(row)


def create(values):
    now = utc_now_iso()
    organization_id = current_organization_id()
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO fleet_rentals (
                organization_id, vehicle_id, damage_case_id, maintenance_id, replacement_vehicle,
                rental_company, contract_number, start_date, expected_end_date,
                end_date, reason, status, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                organization_id,
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
