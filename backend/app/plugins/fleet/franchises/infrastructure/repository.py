from app.core.database import db_session
from app.utils.date_utils import utc_now_iso


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS fleet_franchise_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_id INTEGER NOT NULL,
                damage_case_id INTEGER NOT NULL UNIQUE,
                maintenance_id INTEGER,
                status TEXT NOT NULL,
                motivation TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (vehicle_id) REFERENCES fleet_assets(id),
                FOREIGN KEY (damage_case_id) REFERENCES damage_cases(id),
                FOREIGN KEY (maintenance_id) REFERENCES fleet_maintenances(id)
            );
            CREATE INDEX IF NOT EXISTS idx_franchise_vehicle
                ON fleet_franchise_cases(vehicle_id, updated_at);
            CREATE INDEX IF NOT EXISTS idx_franchise_status
                ON fleet_franchise_cases(status, updated_at);
            """
        )


def _dict(row):
    return {key: row[key] for key in row.keys()} if row else None


def _select() -> str:
    return """
        SELECT f.id, f.vehicle_id, f.damage_case_id,
               COALESCE(m.id, f.maintenance_id) AS maintenance_id,
               f.status, f.motivation, f.notes, f.created_at, f.updated_at,
               a.plate, a.external_identifier,
               a.category AS vehicle_model,
               d.case_number AS damage_case_number,
               d.description AS damage_description,
               m.maintenance_number,
               p.contract_type, p.company, p.owner_company,
               p.contract_number, p.deductible
               , i.id AS insurance_policy_id, i.company AS insurance_company,
               i.policy_number AS insurance_policy_number,
               i.coverage_type AS insurance_coverage_type
        FROM fleet_franchise_cases f
        JOIN fleet_assets a ON a.id = f.vehicle_id
        JOIN damage_cases d ON d.id = f.damage_case_id
        LEFT JOIN fleet_maintenances m ON m.damage_case_id = f.damage_case_id
        LEFT JOIN fleet_asset_profiles p ON p.asset_id = f.vehicle_id
        LEFT JOIN fleet_insurance_policies i ON i.vehicle_id = f.vehicle_id
    """


def get(case_id: int):
    with db_session() as conn:
        row = conn.execute(
            f"{_select()} WHERE f.id = ?",
            (case_id,),
        ).fetchone()
    return _dict(row)


def get_by_damage(damage_case_id: int):
    with db_session() as conn:
        row = conn.execute(
            f"{_select()} WHERE f.damage_case_id = ?",
            (damage_case_id,),
        ).fetchone()
    return _dict(row)


def list_all(vehicle_id: int | None = None):
    where = "WHERE f.vehicle_id = ?" if vehicle_id else ""
    params = (vehicle_id,) if vehicle_id else ()
    with db_session() as conn:
        rows = conn.execute(
            f"""
            {_select()} {where}
            ORDER BY
              CASE f.status
                WHEN 'da_valutare' THEN 0
                WHEN 'in_verifica' THEN 1
                WHEN 'applicata' THEN 2
                WHEN 'non_applicabile' THEN 3
                ELSE 4
              END,
              f.updated_at DESC, f.id DESC
            """,
            params,
        ).fetchall()
    return [_dict(row) for row in rows]


def damage_context(damage_case_id: int):
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT d.id, d.vehicle_id, d.case_number,
                   m.id AS maintenance_id
            FROM damage_cases d
            LEFT JOIN fleet_maintenances m ON m.damage_case_id = d.id
            WHERE d.id = ?
            """,
            (damage_case_id,),
        ).fetchone()
    return _dict(row)


def create(values: dict[str, object]):
    now = utc_now_iso()
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO fleet_franchise_cases (
                vehicle_id, damage_case_id, maintenance_id, status,
                motivation, notes, created_at, updated_at
            ) VALUES (?, ?, ?, 'da_valutare', ?, ?, ?, ?)
            """,
            (
                values["vehicle_id"], values["damage_case_id"],
                values.get("maintenance_id"), values.get("motivation"),
                values.get("notes"), now, now,
            ),
        )
        case_id = int(cursor.lastrowid)
    return get(case_id)


def update(case_id: int, changes: dict[str, object]):
    allowed = {"status", "motivation", "notes"}
    values = {key: value for key, value in changes.items() if key in allowed}
    if not values:
        return get(case_id)
    values["updated_at"] = utc_now_iso()
    with db_session() as conn:
        assignments = ", ".join(f"{key} = ?" for key in values)
        cursor = conn.execute(
            f"UPDATE fleet_franchise_cases SET {assignments} WHERE id = ?",
            [*values.values(), case_id],
        )
        if cursor.rowcount == 0:
            return None
    return get(case_id)
