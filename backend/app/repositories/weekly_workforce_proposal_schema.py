from app.core.config import SETTINGS
from app.core.database import db_session
from app.core.tenant_schema import ensure_column


_ASSIGNMENTS_TABLE = "weekly_workforce_proposal_assignments"
_GAPS_TABLE = "weekly_workforce_proposal_gaps"


def _column_names(conn, table: str) -> set[str]:
    if SETTINGS.database_backend == "postgresql":
        rows = conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = ?
            """,
            (table,),
        ).fetchall()
        return {row["column_name"] for row in rows}
    return {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _evolve_existing_schema(conn) -> None:
    assignment_columns = _column_names(conn, _ASSIGNMENTS_TABLE)
    if "demand_trace_id" not in assignment_columns:
        row = conn.execute(
            f"SELECT COUNT(*) AS total FROM {_ASSIGNMENTS_TABLE}"
        ).fetchone()
        if row["total"]:
            raise RuntimeError(
                "cannot add assignment demand_trace_id: existing rows have "
                "no authoritative demand trace"
            )
        ensure_column(
            conn,
            _ASSIGNMENTS_TABLE,
            "demand_trace_id",
            "TEXT NOT NULL",
        )

    ensure_column(conn, _GAPS_TABLE, "starts_at", "TEXT")
    ensure_column(conn, _GAPS_TABLE, "ends_at", "TEXT")


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS weekly_planning_input_snapshots (
                organization_id TEXT NOT NULL,
                snapshot_id TEXT NOT NULL,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                operational_unit_identifier TEXT NOT NULL,
                operational_unit_name TEXT,
                policy_set_identifier TEXT NOT NULL,
                policy_set_version TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (organization_id, snapshot_id),
                UNIQUE (organization_id, snapshot_id, fingerprint)
            );

            CREATE TABLE IF NOT EXISTS weekly_workforce_proposals (
                organization_id TEXT NOT NULL,
                proposal_id TEXT NOT NULL,
                version INTEGER NOT NULL CHECK (version > 0),
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                operational_unit_identifier TEXT NOT NULL,
                operational_unit_name TEXT,
                input_snapshot_id TEXT NOT NULL,
                input_fingerprint TEXT NOT NULL,
                policy_set_identifier TEXT NOT NULL,
                policy_set_version TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (organization_id, proposal_id, version),
                FOREIGN KEY (
                    organization_id, input_snapshot_id, input_fingerprint
                ) REFERENCES weekly_planning_input_snapshots (
                    organization_id, snapshot_id, fingerprint
                ) ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS weekly_workforce_proposal_assignments (
                organization_id TEXT NOT NULL,
                proposal_id TEXT NOT NULL,
                proposal_version INTEGER NOT NULL,
                assignment_id TEXT NOT NULL,
                demand_trace_id TEXT NOT NULL,
                workforce_member_id TEXT NOT NULL,
                operational_date TEXT NOT NULL,
                operational_unit_identifier TEXT NOT NULL,
                operational_unit_name TEXT,
                time_window_identifier TEXT NOT NULL,
                starts_at TEXT,
                ends_at TEXT,
                capability_or_workload TEXT NOT NULL,
                shift_identifier TEXT,
                origin TEXT NOT NULL,
                status TEXT NOT NULL,
                deterministic_priority INTEGER NOT NULL
                    CHECK (deterministic_priority >= 0),
                locked INTEGER NOT NULL CHECK (locked IN (0, 1)),
                reasons_json TEXT NOT NULL,
                PRIMARY KEY (
                    organization_id, proposal_id, proposal_version,
                    assignment_id
                ),
                FOREIGN KEY (
                    organization_id, proposal_id, proposal_version
                ) REFERENCES weekly_workforce_proposals (
                    organization_id, proposal_id, version
                ) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS weekly_workforce_proposal_gaps (
                organization_id TEXT NOT NULL,
                proposal_id TEXT NOT NULL,
                proposal_version INTEGER NOT NULL,
                demand_trace_id TEXT NOT NULL,
                operational_date TEXT NOT NULL,
                operational_unit_identifier TEXT NOT NULL,
                operational_unit_name TEXT,
                time_window_identifier TEXT NOT NULL,
                starts_at TEXT,
                ends_at TEXT,
                capability_or_workload TEXT NOT NULL,
                required_quantity INTEGER NOT NULL,
                proposed_quantity INTEGER NOT NULL,
                gap_quantity INTEGER NOT NULL,
                reasons_json TEXT NOT NULL,
                PRIMARY KEY (
                    organization_id, proposal_id, proposal_version,
                    demand_trace_id
                ),
                FOREIGN KEY (
                    organization_id, proposal_id, proposal_version
                ) REFERENCES weekly_workforce_proposals (
                    organization_id, proposal_id, version
                ) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS weekly_workforce_proposal_explainability (
                organization_id TEXT NOT NULL,
                proposal_id TEXT NOT NULL,
                proposal_version INTEGER NOT NULL,
                demand_trace_id TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
                workforce_member_id TEXT,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (
                    organization_id, proposal_id, proposal_version,
                    demand_trace_id, artifact_type, ordinal
                ),
                FOREIGN KEY (
                    organization_id, proposal_id, proposal_version
                ) REFERENCES weekly_workforce_proposals (
                    organization_id, proposal_id, version
                ) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS weekly_workforce_proposal_events (
                organization_id TEXT NOT NULL,
                proposal_id TEXT NOT NULL,
                proposal_version INTEGER NOT NULL,
                event_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor_id TEXT,
                reason TEXT,
                payload_json TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY (
                    organization_id, proposal_id, proposal_version, event_id
                ),
                FOREIGN KEY (
                    organization_id, proposal_id, proposal_version
                ) REFERENCES weekly_workforce_proposals (
                    organization_id, proposal_id, version
                ) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_weekly_proposals_logical_identity
                ON weekly_workforce_proposals (organization_id, proposal_id);

            CREATE INDEX IF NOT EXISTS idx_weekly_assignments_revision
                ON weekly_workforce_proposal_assignments (
                    organization_id, proposal_id, proposal_version
                );
            CREATE INDEX IF NOT EXISTS idx_weekly_assignments_member
                ON weekly_workforce_proposal_assignments (
                    organization_id, workforce_member_id
                );

            CREATE INDEX IF NOT EXISTS idx_weekly_gaps_revision
                ON weekly_workforce_proposal_gaps (
                    organization_id, proposal_id, proposal_version
                );

            CREATE INDEX IF NOT EXISTS idx_weekly_explainability_revision
                ON weekly_workforce_proposal_explainability (
                    organization_id, proposal_id, proposal_version
                );
            CREATE INDEX IF NOT EXISTS idx_weekly_explainability_demand
                ON weekly_workforce_proposal_explainability (
                    organization_id, demand_trace_id
                );

            CREATE INDEX IF NOT EXISTS idx_weekly_snapshots_fingerprint
                ON weekly_planning_input_snapshots (
                    organization_id, fingerprint
                );
            """
        )
        _evolve_existing_schema(conn)
