from app.core.database import PostgresConnection, db_session


PROFILE_COLUMNS = {
    "first_name": "TEXT",
    "last_name": "TEXT",
    "station": "TEXT",
    "operational_notes": "TEXT",
    "is_reserve": "INTEGER NOT NULL DEFAULT 0",
}


def _ensure_profile_columns(conn) -> None:
    if isinstance(conn, PostgresConnection):
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
            ("workforce_members",),
        ).fetchall()
        existing = {row["column_name"] for row in rows}
    else:
        existing = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(workforce_members)").fetchall()
        }
    for name, definition in PROFILE_COLUMNS.items():
        if name not in existing:
            conn.execute(
                f"ALTER TABLE workforce_members ADD COLUMN {name} {definition}"
            )


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS workforce_imports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL UNIQUE,
                original_filename TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                sheets TEXT NOT NULL,
                summary TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS workforce_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_identifier TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                role TEXT,
                employment_type TEXT,
                contract_start TEXT,
                contract_end TEXT,
                weekly_hours REAL,
                capabilities TEXT NOT NULL,
                active INTEGER NOT NULL,
                source_reference TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS workforce_day_statuses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workforce_member_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                status_code TEXT NOT NULL,
                availability INTEGER NOT NULL,
                shift_code TEXT,
                start_time TEXT,
                end_time TEXT,
                notes TEXT,
                source_reference TEXT NOT NULL,
                observed_or_confirmed TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (workforce_member_id) REFERENCES workforce_members(id)
                    ON DELETE CASCADE,
                UNIQUE (workforce_member_id, date)
            );

            CREATE TABLE IF NOT EXISTS workforce_requirements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                operational_unit_id TEXT NOT NULL,
                required_resources INTEGER NOT NULL,
                required_capabilities TEXT NOT NULL,
                source TEXT NOT NULL,
                version INTEGER NOT NULL,
                UNIQUE (date, operational_unit_id)
            );

            CREATE TABLE IF NOT EXISTS workforce_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                actor TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                before_value TEXT,
                after_value TEXT NOT NULL,
                reason TEXT NOT NULL,
                source TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_workforce_status_date
                ON workforce_day_statuses(date, workforce_member_id);
            CREATE INDEX IF NOT EXISTS idx_workforce_requirement_date
                ON workforce_requirements(date, operational_unit_id);
            CREATE INDEX IF NOT EXISTS idx_workforce_changes_time
                ON workforce_changes(timestamp, id);
            """
        )
        _ensure_profile_columns(conn)
