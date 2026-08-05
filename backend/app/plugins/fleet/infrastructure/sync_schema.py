from app.core.database import db_session
from app.core.tenant_schema import ensure_column


def init_sync_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS fleet_asset_metadata (
                asset_id INTEGER PRIMARY KEY,
                vehicle_model TEXT,
                rental_company TEXT,
                observed_assigned_human_resource TEXT,
                observed_second_human_resource TEXT,
                replacement_asset_reference TEXT,
                parking_location TEXT,
                alternative_identifiers TEXT NOT NULL,
                source_reference TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (asset_id) REFERENCES fleet_assets(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS fleet_sync_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id TEXT,
                application_key TEXT NOT NULL UNIQUE,
                workbook_fingerprint TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                import_id INTEGER NOT NULL,
                summary TEXT NOT NULL,
                FOREIGN KEY (import_id) REFERENCES imports(id)
            );

            CREATE TABLE IF NOT EXISTS fleet_sync_event_fingerprints (
                fingerprint TEXT PRIMARY KEY,
                event_id INTEGER NOT NULL,
                FOREIGN KEY (event_id) REFERENCES fleet_asset_events(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_fleet_sync_workbook
                ON fleet_sync_runs(workbook_fingerprint, id);
            """
        )
        ensure_column(conn, "fleet_sync_runs", "organization_id", "TEXT")
        owner = conn.execute(
            "SELECT id FROM organizations ORDER BY created_at ASC, id ASC LIMIT 1"
        ).fetchone()
        if owner:
            conn.execute(
                """
                UPDATE fleet_sync_runs SET organization_id=?
                WHERE organization_id IS NULL OR organization_id='default'
                """,
                (owner["id"],),
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fleet_sync_organization "
            "ON fleet_sync_runs(organization_id, id)"
        )
