from app.core.database import db_session
from app.utils.date_utils import utc_now_iso


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS fleet_insurance_policies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_id INTEGER NOT NULL UNIQUE,
                company TEXT NOT NULL,
                policy_number TEXT NOT NULL UNIQUE,
                coverage_type TEXT NOT NULL,
                starts_on TEXT NOT NULL,
                expires_on TEXT NOT NULL,
                coverage_limit TEXT,
                insurance_deductible TEXT,
                notes TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (vehicle_id) REFERENCES fleet_assets(id)
            );
            CREATE INDEX IF NOT EXISTS idx_insurance_status
                ON fleet_insurance_policies(status, expires_on);
            """
        )


def _dict(row):
    return {key: row[key] for key in row.keys()} if row else None


def _select() -> str:
    return """
        SELECT p.*, a.plate, a.external_identifier,
               a.category AS vehicle_model
        FROM fleet_insurance_policies p
        JOIN fleet_assets a ON a.id = p.vehicle_id
    """


def get(policy_id: int):
    with db_session() as conn:
        row = conn.execute(
            f"{_select()} WHERE p.id = ?",
            (policy_id,),
        ).fetchone()
    return _dict(row)


def get_by_vehicle(vehicle_id: int):
    with db_session() as conn:
        row = conn.execute(
            f"{_select()} WHERE p.vehicle_id = ?",
            (vehicle_id,),
        ).fetchone()
    return _dict(row)


def list_all(vehicle_id: int | None = None):
    where = "WHERE p.vehicle_id = ?" if vehicle_id else ""
    params = (vehicle_id,) if vehicle_id else ()
    with db_session() as conn:
        rows = conn.execute(
            f"""
            {_select()} {where}
            ORDER BY
              CASE p.status
                WHEN 'scaduta' THEN 0
                WHEN 'in_scadenza' THEN 1
                WHEN 'attiva' THEN 2
                ELSE 3
              END,
              p.expires_on ASC, p.id DESC
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
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO fleet_insurance_policies (
                vehicle_id, company, policy_number, coverage_type,
                starts_on, expires_on, coverage_limit,
                insurance_deductible, notes, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["vehicle_id"], values["company"], values["policy_number"],
                values["coverage_type"], values["starts_on"], values["expires_on"],
                values.get("coverage_limit"), values.get("insurance_deductible"),
                values.get("notes"), values["status"], now, now,
            ),
        )
        policy_id = int(cursor.lastrowid)
    return get(policy_id)


def update(policy_id: int, changes: dict[str, object]):
    allowed = {
        "company", "policy_number", "coverage_type", "starts_on", "expires_on",
        "coverage_limit", "insurance_deductible", "notes", "status",
    }
    values = {key: value for key, value in changes.items() if key in allowed}
    if not values:
        return get(policy_id)
    values["updated_at"] = utc_now_iso()
    with db_session() as conn:
        assignments = ", ".join(f"{key} = ?" for key in values)
        cursor = conn.execute(
            f"UPDATE fleet_insurance_policies SET {assignments} WHERE id = ?",
            [*values.values(), policy_id],
        )
        if cursor.rowcount == 0:
            return None
    return get(policy_id)
