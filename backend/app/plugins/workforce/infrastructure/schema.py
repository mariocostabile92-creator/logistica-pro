from app.core.database import PostgresConnection, db_session


PROFILE_COLUMNS = {
    "first_name": "TEXT",
    "last_name": "TEXT",
    "station": "TEXT",
    "operational_notes": "TEXT",
    "is_reserve": "INTEGER NOT NULL DEFAULT 0",
    "phone": "TEXT",
    "email": "TEXT",
    "organization_id": "TEXT NOT NULL DEFAULT 'default'",
}

SCOPED_COLUMNS = {
    "workforce_imports": {"organization_id": "TEXT NOT NULL DEFAULT 'default'"},
    "workforce_day_statuses": {"organization_id": "TEXT NOT NULL DEFAULT 'default'"},
    "workforce_requirements": {"organization_id": "TEXT NOT NULL DEFAULT 'default'"},
    "workforce_changes": {"organization_id": "TEXT NOT NULL DEFAULT 'default'"},
}


def _sqlite_table_definition(conn, table: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return str(row["sql"] or "").upper() if row else ""


def _migrate_sqlite_scoped_uniqueness(conn) -> None:
    legacy_members = (
        "EXTERNAL_IDENTIFIER TEXT NOT NULL UNIQUE"
        in _sqlite_table_definition(conn, "workforce_members")
    )
    legacy_imports = (
        "FINGERPRINT TEXT NOT NULL UNIQUE"
        in _sqlite_table_definition(conn, "workforce_imports")
    )
    legacy_requirements = (
        "UNIQUE (DATE, OPERATIONAL_UNIT_ID)"
        in _sqlite_table_definition(conn, "workforce_requirements")
    )
    if not any((legacy_members, legacy_imports, legacy_requirements)):
        return

    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("PRAGMA legacy_alter_table = ON")
    try:
        if legacy_members:
            conn.executescript(
                """
                ALTER TABLE workforce_members RENAME TO workforce_members_global_identity;
                CREATE TABLE workforce_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    external_identifier TEXT NOT NULL,
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
                    updated_at TEXT NOT NULL,
                    first_name TEXT,
                    last_name TEXT,
                    station TEXT,
                    operational_notes TEXT,
                    is_reserve INTEGER NOT NULL DEFAULT 0,
                    organization_id TEXT NOT NULL DEFAULT 'default',
                    UNIQUE (organization_id, external_identifier)
                );
                INSERT INTO workforce_members (
                    id, external_identifier, display_name, role, employment_type,
                    contract_start, contract_end, weekly_hours, capabilities,
                    active, source_reference, created_at, updated_at, first_name,
                    last_name, station, operational_notes, is_reserve,
                    organization_id
                )
                SELECT id, external_identifier, display_name, role, employment_type,
                       contract_start, contract_end, weekly_hours, capabilities,
                       active, source_reference, created_at, updated_at, first_name,
                       last_name, station, operational_notes, is_reserve,
                       organization_id
                FROM workforce_members_global_identity;
                DROP TABLE workforce_members_global_identity;
                """
            )
        if legacy_imports:
            conn.executescript(
                """
                ALTER TABLE workforce_imports RENAME TO workforce_imports_global_fingerprint;
                CREATE TABLE workforce_imports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    imported_at TEXT NOT NULL,
                    sheets TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    organization_id TEXT NOT NULL DEFAULT 'default',
                    UNIQUE (organization_id, fingerprint)
                );
                INSERT INTO workforce_imports (
                    id, fingerprint, original_filename, imported_at, sheets,
                    summary, organization_id
                )
                SELECT id, fingerprint, original_filename, imported_at, sheets,
                       summary, organization_id
                FROM workforce_imports_global_fingerprint;
                DROP TABLE workforce_imports_global_fingerprint;
                """
            )
        if legacy_requirements:
            conn.executescript(
                """
                ALTER TABLE workforce_requirements RENAME TO workforce_requirements_global_identity;
                CREATE TABLE workforce_requirements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    operational_unit_id TEXT NOT NULL,
                    required_resources INTEGER NOT NULL,
                    required_capabilities TEXT NOT NULL,
                    source TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    organization_id TEXT NOT NULL DEFAULT 'default',
                    UNIQUE (organization_id, date, operational_unit_id)
                );
                INSERT INTO workforce_requirements (
                    id, date, operational_unit_id, required_resources,
                    required_capabilities, source, version, organization_id
                )
                SELECT id, date, operational_unit_id, required_resources,
                       required_capabilities, source, version, organization_id
                FROM workforce_requirements_global_identity;
                DROP TABLE workforce_requirements_global_identity;
                """
            )
    finally:
        conn.execute("PRAGMA legacy_alter_table = OFF")
        conn.execute("PRAGMA foreign_keys = ON")


def _ensure_scoped_uniqueness(conn, database_backend: str | None = None) -> None:
    is_postgres = (
        database_backend == "postgresql" or isinstance(conn, PostgresConnection)
    )
    if is_postgres:
        conn.execute(
            "ALTER TABLE workforce_members DROP CONSTRAINT IF EXISTS "
            "workforce_members_external_identifier_key"
        )
        conn.execute(
            "ALTER TABLE workforce_imports DROP CONSTRAINT IF EXISTS "
            "workforce_imports_fingerprint_key"
        )
        conn.execute(
            "ALTER TABLE workforce_requirements DROP CONSTRAINT IF EXISTS "
            "workforce_requirements_date_operational_unit_id_key"
        )
    else:
        _migrate_sqlite_scoped_uniqueness(conn)

    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_workforce_members_org_external "
        "ON workforce_members(organization_id, LOWER(external_identifier))"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_workforce_imports_org_fingerprint "
        "ON workforce_imports(organization_id, fingerprint)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_workforce_requirements_org_identity "
        "ON workforce_requirements(organization_id, date, operational_unit_id)"
    )


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


def _ensure_columns(conn, table: str, columns: dict[str, str]) -> None:
    if isinstance(conn, PostgresConnection):
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
            (table,),
        ).fetchall()
        existing = {row["column_name"] for row in rows}
    else:
        existing = {
            row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS workforce_imports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                sheets TEXT NOT NULL,
                summary TEXT NOT NULL,
                organization_id TEXT NOT NULL DEFAULT 'default',
                UNIQUE (organization_id, fingerprint)
            );

            CREATE UNIQUE INDEX IF NOT EXISTS uq_workforce_imports_id_org
                ON workforce_imports(id, organization_id);

            CREATE TABLE IF NOT EXISTS driver_shift_plannings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id TEXT NOT NULL,
                label TEXT,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                status TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (id, organization_id)
            );

            CREATE TABLE IF NOT EXISTS driver_shift_planning_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id TEXT NOT NULL,
                driver_shift_planning_id INTEGER NOT NULL,
                workforce_import_id INTEGER NOT NULL,
                source_order INTEGER NOT NULL DEFAULT 0,
                added_at TEXT NOT NULL,
                added_by TEXT NOT NULL,
                status TEXT NOT NULL,
                FOREIGN KEY (driver_shift_planning_id, organization_id)
                    REFERENCES driver_shift_plannings(id, organization_id)
                    ON DELETE CASCADE,
                FOREIGN KEY (workforce_import_id, organization_id)
                    REFERENCES workforce_imports(id, organization_id)
                    ON DELETE RESTRICT,
                UNIQUE (driver_shift_planning_id, workforce_import_id)
            );

            CREATE TABLE IF NOT EXISTS workforce_import_rows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id TEXT NOT NULL,
                workforce_import_id INTEGER NOT NULL,
                source_sheet TEXT NOT NULL,
                source_row_number INTEGER NOT NULL,
                source_reference TEXT NOT NULL,
                source_record_key TEXT NOT NULL,
                row_kind TEXT NOT NULL,
                source_external_identifier TEXT,
                driver_display_name TEXT,
                transporter_id TEXT,
                station TEXT,
                operational_date TEXT,
                status_code TEXT,
                availability INTEGER,
                shift_code TEXT,
                start_time TEXT,
                end_time TEXT,
                notes TEXT,
                employment_type TEXT,
                contract_start TEXT,
                contract_end TEXT,
                weekly_hours REAL,
                resolved_workforce_member_id INTEGER,
                raw_payload TEXT NOT NULL,
                FOREIGN KEY (workforce_import_id, organization_id)
                    REFERENCES workforce_imports(id, organization_id)
                    ON DELETE CASCADE,
                UNIQUE (
                    workforce_import_id, source_sheet,
                    source_row_number, source_record_key
                )
            );

            CREATE TABLE IF NOT EXISTS workforce_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_identifier TEXT NOT NULL,
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
                updated_at TEXT NOT NULL,
                organization_id TEXT NOT NULL DEFAULT 'default',
                UNIQUE (organization_id, external_identifier)
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
                organization_id TEXT NOT NULL DEFAULT 'default',
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
                organization_id TEXT NOT NULL DEFAULT 'default',
                UNIQUE (organization_id, date, operational_unit_id)
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
                source TEXT NOT NULL,
                organization_id TEXT NOT NULL DEFAULT 'default'
            );

            CREATE TABLE IF NOT EXISTS driver_shift_planning_resolutions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id TEXT NOT NULL,
                driver_shift_planning_id INTEGER NOT NULL,
                planning_version INTEGER NOT NULL,
                conflict_key TEXT NOT NULL,
                resolution_type TEXT NOT NULL,
                selected_source_row_id INTEGER,
                resolved_payload TEXT,
                actor TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (driver_shift_planning_id, organization_id)
                    REFERENCES driver_shift_plannings(id, organization_id)
                    ON DELETE CASCADE,
                FOREIGN KEY (selected_source_row_id)
                    REFERENCES workforce_import_rows(id) ON DELETE RESTRICT,
                UNIQUE (driver_shift_planning_id, planning_version, conflict_key)
            );

            CREATE TABLE IF NOT EXISTS driver_shift_planning_published_rows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id TEXT NOT NULL,
                driver_shift_planning_id INTEGER NOT NULL,
                planning_version INTEGER NOT NULL,
                workforce_member_id INTEGER NOT NULL,
                operational_date TEXT NOT NULL,
                status_code TEXT NOT NULL,
                availability INTEGER NOT NULL,
                shift_code TEXT,
                start_time TEXT,
                end_time TEXT,
                station TEXT,
                transporter_id TEXT,
                provenance_summary TEXT NOT NULL,
                selected_source_row_id INTEGER,
                published_at TEXT NOT NULL,
                FOREIGN KEY (driver_shift_planning_id, organization_id)
                    REFERENCES driver_shift_plannings(id, organization_id)
                    ON DELETE CASCADE,
                FOREIGN KEY (workforce_member_id) REFERENCES workforce_members(id)
                    ON DELETE RESTRICT,
                FOREIGN KEY (selected_source_row_id)
                    REFERENCES workforce_import_rows(id) ON DELETE RESTRICT,
                UNIQUE (
                    driver_shift_planning_id, planning_version,
                    workforce_member_id, operational_date
                )
            );

            CREATE TABLE IF NOT EXISTS driver_shift_distributions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id TEXT NOT NULL,
                driver_shift_planning_id INTEGER NOT NULL,
                planning_version INTEGER NOT NULL,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (driver_shift_planning_id, organization_id)
                    REFERENCES driver_shift_plannings(id, organization_id)
                    ON DELETE CASCADE,
                UNIQUE (organization_id, driver_shift_planning_id, planning_version),
                UNIQUE (id, organization_id)
            );

            CREATE TABLE IF NOT EXISTS driver_shift_distribution_recipients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                public_id TEXT NOT NULL UNIQUE,
                organization_id TEXT NOT NULL,
                distribution_id INTEGER NOT NULL,
                workforce_member_id INTEGER NOT NULL,
                delivery_status TEXT NOT NULL,
                access_status TEXT NOT NULL,
                access_token_hash TEXT NOT NULL UNIQUE,
                access_generation INTEGER NOT NULL,
                access_expires_at TEXT NOT NULL,
                access_revoked_at TEXT,
                first_opened_at TEXT,
                last_opened_at TEXT,
                acknowledged_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (distribution_id, organization_id)
                    REFERENCES driver_shift_distributions(id, organization_id)
                    ON DELETE CASCADE,
                FOREIGN KEY (workforce_member_id) REFERENCES workforce_members(id)
                    ON DELETE RESTRICT,
                UNIQUE (distribution_id, workforce_member_id)
            );

            CREATE TABLE IF NOT EXISTS driver_shift_distribution_portals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id TEXT NOT NULL,
                distribution_id INTEGER NOT NULL,
                public_id TEXT NOT NULL UNIQUE,
                token_hash TEXT NOT NULL UNIQUE,
                token_generation INTEGER NOT NULL,
                status TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                revoked_at TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (distribution_id, organization_id)
                    REFERENCES driver_shift_distributions(id, organization_id)
                    ON DELETE CASCADE,
                UNIQUE (organization_id, distribution_id)
            );

            CREATE TABLE IF NOT EXISTS driver_shift_driver_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id TEXT NOT NULL,
                workforce_member_id INTEGER NOT NULL,
                credential_status TEXT NOT NULL,
                access_code_hash TEXT NOT NULL UNIQUE,
                pin_hash TEXT NOT NULL,
                generation INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                reset_at TEXT,
                revoked_at TEXT,
                FOREIGN KEY (workforce_member_id) REFERENCES workforce_members(id)
                    ON DELETE CASCADE,
                UNIQUE (organization_id, workforce_member_id),
                UNIQUE (id, organization_id)
            );

            CREATE TABLE IF NOT EXISTS driver_shift_driver_sessions (
                id TEXT PRIMARY KEY,
                session_token_hash TEXT NOT NULL UNIQUE,
                organization_id TEXT NOT NULL,
                workforce_member_id INTEGER NOT NULL,
                distribution_id INTEGER NOT NULL,
                portal_id INTEGER NOT NULL,
                portal_generation INTEGER NOT NULL,
                credential_generation INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                revoked_at TEXT,
                remember_device INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (distribution_id, organization_id)
                    REFERENCES driver_shift_distributions(id, organization_id)
                    ON DELETE CASCADE,
                FOREIGN KEY (portal_id) REFERENCES driver_shift_distribution_portals(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (workforce_member_id) REFERENCES workforce_members(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS driver_shift_login_attempts (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                portal_id INTEGER NOT NULL,
                access_code_fingerprint TEXT NOT NULL,
                ip_fingerprint TEXT NOT NULL,
                attempted_at TEXT NOT NULL,
                succeeded INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (portal_id) REFERENCES driver_shift_distribution_portals(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_workforce_status_date
                ON workforce_day_statuses(date, workforce_member_id);
            CREATE INDEX IF NOT EXISTS idx_workforce_requirement_date
                ON workforce_requirements(date, operational_unit_id);
            CREATE INDEX IF NOT EXISTS idx_workforce_changes_time
                ON workforce_changes(timestamp, id);
            CREATE INDEX IF NOT EXISTS idx_workforce_import_rows_scope
                ON workforce_import_rows(organization_id, workforce_import_id);
            CREATE INDEX IF NOT EXISTS idx_workforce_import_rows_identity
                ON workforce_import_rows(
                    organization_id, transporter_id,
                    source_external_identifier
                );
            CREATE INDEX IF NOT EXISTS idx_workforce_import_rows_driver_date
                ON workforce_import_rows(
                    organization_id, resolved_workforce_member_id,
                    operational_date
                );
            CREATE INDEX IF NOT EXISTS idx_driver_shift_plannings_scope
                ON driver_shift_plannings(
                    organization_id, period_start, period_end, status
                );
            CREATE INDEX IF NOT EXISTS idx_driver_shift_planning_sources_scope
                ON driver_shift_planning_sources(
                    organization_id, driver_shift_planning_id, source_order
                );
            CREATE INDEX IF NOT EXISTS idx_driver_shift_planning_resolutions_scope
                ON driver_shift_planning_resolutions(
                    organization_id, driver_shift_planning_id,
                    planning_version, conflict_key
                );
            CREATE INDEX IF NOT EXISTS idx_driver_shift_published_member_date
                ON driver_shift_planning_published_rows(
                    organization_id, workforce_member_id, operational_date
                );
            CREATE INDEX IF NOT EXISTS idx_driver_shift_distribution_scope
                ON driver_shift_distributions(
                    organization_id, driver_shift_planning_id,
                    planning_version, status
                );
            CREATE INDEX IF NOT EXISTS idx_driver_shift_recipient_scope
                ON driver_shift_distribution_recipients(
                    organization_id, distribution_id, workforce_member_id
                );
            CREATE INDEX IF NOT EXISTS idx_driver_shift_recipient_token
                ON driver_shift_distribution_recipients(access_token_hash);
            CREATE INDEX IF NOT EXISTS idx_driver_shift_portal_scope
                ON driver_shift_distribution_portals(
                    organization_id, distribution_id, status
                );
            CREATE INDEX IF NOT EXISTS idx_driver_shift_portal_token
                ON driver_shift_distribution_portals(token_hash);
            CREATE INDEX IF NOT EXISTS idx_driver_shift_credential_scope
                ON driver_shift_driver_credentials(
                    organization_id, workforce_member_id, credential_status
                );
            CREATE INDEX IF NOT EXISTS idx_driver_shift_driver_session_token
                ON driver_shift_driver_sessions(session_token_hash);
            CREATE INDEX IF NOT EXISTS idx_driver_shift_driver_session_scope
                ON driver_shift_driver_sessions(
                    organization_id, workforce_member_id, distribution_id
                );
            CREATE INDEX IF NOT EXISTS idx_driver_shift_login_attempt_code
                ON driver_shift_login_attempts(
                    portal_id, access_code_fingerprint, attempted_at
                );
            CREATE INDEX IF NOT EXISTS idx_driver_shift_login_attempt_ip
                ON driver_shift_login_attempts(
                    portal_id, ip_fingerprint, attempted_at
                );

            CREATE TABLE IF NOT EXISTS workforce_consecutivity_policies (
                organization_id TEXT PRIMARY KEY,
                warning_threshold INTEGER NOT NULL,
                rest_required_threshold INTEGER NOT NULL,
                rest_break_days INTEGER NOT NULL,
                updated_by TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS workforce_consecutivity_overrides (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                workforce_member_id INTEGER NOT NULL,
                operation_date TEXT NOT NULL,
                valid_until TEXT NOT NULL,
                target_callability TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY (workforce_member_id) REFERENCES workforce_members(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_workforce_policy_override_scope
                ON workforce_consecutivity_overrides(
                    organization_id, workforce_member_id,
                    operation_date, valid_until
                );
            """
        )
        _ensure_profile_columns(conn)
        for table, columns in SCOPED_COLUMNS.items():
            _ensure_columns(conn, table, columns)
        _ensure_columns(conn, "driver_shift_plannings", {
            "published_at": "TEXT",
            "published_by": "TEXT",
            "revision_of_planning_id": "INTEGER",
        })
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_workforce_member_org ON workforce_members(organization_id, active)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_workforce_status_org_date ON workforce_day_statuses(organization_id, date, workforce_member_id)"
        )
        organization = conn.execute(
            "SELECT id FROM organizations ORDER BY created_at LIMIT 1"
        ).fetchone()
        if organization:
            organization_id = organization["id"]
            for table in (
                "workforce_imports", "workforce_members",
                "workforce_day_statuses", "workforce_requirements",
                "workforce_changes",
            ):
                conn.execute(
                    f"UPDATE {table} SET organization_id = ? WHERE organization_id = 'default'",
                    (organization_id,),
                )
        _ensure_scoped_uniqueness(conn)
