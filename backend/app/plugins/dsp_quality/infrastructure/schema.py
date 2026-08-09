from app.core.database import db_session
from app.plugins.dsp_quality.domain.metric_catalog import METRIC_DEFINITIONS


def init_schema() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS dsp_quality_scorecards (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                source_provider TEXT NOT NULL,
                dsp_identifier TEXT NOT NULL,
                station TEXT NOT NULL,
                reported_year INTEGER NOT NULL,
                reported_week INTEGER NOT NULL,
                geography TEXT,
                active_revision_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (
                    organization_id, source_provider, dsp_identifier,
                    station, reported_year, reported_week
                )
            );

            CREATE TABLE IF NOT EXISTS dsp_quality_metric_definitions (
                metric_key TEXT PRIMARY KEY,
                canonical_label TEXT NOT NULL,
                category TEXT NOT NULL,
                value_type TEXT NOT NULL,
                unit TEXT,
                direction TEXT NOT NULL,
                scope TEXT NOT NULL,
                provider TEXT NOT NULL,
                definition_version TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS dsp_quality_standard_sets (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                geography_scope TEXT,
                station_scope TEXT,
                detected_source_version TEXT,
                effective_from TEXT,
                effective_to TEXT,
                source_fingerprint TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dsp_quality_scorecard_versions (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                scorecard_id TEXT NOT NULL,
                source_filename TEXT NOT NULL,
                source_fingerprint_sha256 TEXT NOT NULL,
                parser_adapter TEXT NOT NULL,
                parser_version TEXT NOT NULL,
                detected_template_version TEXT,
                imported_at TEXT NOT NULL,
                imported_by TEXT NOT NULL,
                status TEXT NOT NULL,
                source_attachment_reference TEXT,
                rank INTEGER,
                rank_wow_declared INTEGER,
                overall_score TEXT,
                overall_standing TEXT,
                raw_period_label TEXT,
                active INTEGER NOT NULL DEFAULT 0,
                standard_set_id TEXT,
                working_hours_section_present INTEGER NOT NULL DEFAULT 0,
                working_hours_exception_count INTEGER NOT NULL DEFAULT 0,
                UNIQUE (organization_id, source_fingerprint_sha256),
                FOREIGN KEY (scorecard_id) REFERENCES dsp_quality_scorecards(id),
                FOREIGN KEY (standard_set_id) REFERENCES dsp_quality_standard_sets(id)
            );

            CREATE TABLE IF NOT EXISTS dsp_quality_metric_observations (
                id TEXT PRIMARY KEY,
                revision_id TEXT NOT NULL,
                metric_key TEXT NOT NULL,
                raw_value TEXT,
                normalized_numeric_value TEXT,
                normalized_text_value TEXT,
                value_state TEXT NOT NULL,
                rating TEXT,
                compliance_state TEXT,
                normalization_rule_version TEXT NOT NULL,
                source_page INTEGER,
                source_table TEXT,
                source_row TEXT,
                source_column TEXT,
                extracted_label TEXT,
                UNIQUE (revision_id, metric_key),
                FOREIGN KEY (revision_id) REFERENCES dsp_quality_scorecard_versions(id),
                FOREIGN KEY (metric_key) REFERENCES dsp_quality_metric_definitions(metric_key)
            );

            CREATE TABLE IF NOT EXISTS dsp_quality_section_standings (
                id TEXT PRIMARY KEY,
                revision_id TEXT NOT NULL,
                section_key TEXT NOT NULL,
                section_label TEXT NOT NULL,
                standing TEXT NOT NULL,
                source_page INTEGER,
                UNIQUE (revision_id, section_key),
                FOREIGN KEY (revision_id) REFERENCES dsp_quality_scorecard_versions(id)
            );

            CREATE TABLE IF NOT EXISTS dsp_quality_transporter_rows (
                id TEXT PRIMARY KEY,
                revision_id TEXT NOT NULL,
                transporter_external_id TEXT NOT NULL,
                row_index INTEGER NOT NULL,
                workforce_member_id INTEGER,
                mapping_status TEXT NOT NULL,
                source_page INTEGER,
                raw_row_fingerprint TEXT,
                UNIQUE (revision_id, row_index),
                UNIQUE (revision_id, transporter_external_id),
                FOREIGN KEY (revision_id) REFERENCES dsp_quality_scorecard_versions(id),
                FOREIGN KEY (workforce_member_id) REFERENCES workforce_members(id)
            );

            CREATE TABLE IF NOT EXISTS dsp_quality_transporter_observations (
                id TEXT PRIMARY KEY,
                transporter_row_id TEXT NOT NULL,
                metric_key TEXT NOT NULL,
                raw_value TEXT,
                normalized_numeric_value TEXT,
                normalized_text_value TEXT,
                value_state TEXT NOT NULL,
                rating TEXT,
                compliance_state TEXT,
                normalization_rule_version TEXT NOT NULL,
                source_page INTEGER,
                source_column TEXT,
                UNIQUE (transporter_row_id, metric_key),
                FOREIGN KEY (transporter_row_id) REFERENCES dsp_quality_transporter_rows(id),
                FOREIGN KEY (metric_key) REFERENCES dsp_quality_metric_definitions(metric_key)
            );

            CREATE TABLE IF NOT EXISTS workforce_external_identities (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                workforce_member_id INTEGER,
                status TEXT NOT NULL,
                valid_from TEXT,
                valid_to TEXT,
                verified_by TEXT,
                verified_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (organization_id, source, external_id),
                FOREIGN KEY (workforce_member_id) REFERENCES workforce_members(id)
            );

            CREATE TABLE IF NOT EXISTS workforce_external_identity_events (
                id TEXT PRIMARY KEY,
                identity_id TEXT NOT NULL,
                organization_id TEXT NOT NULL,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (identity_id) REFERENCES workforce_external_identities(id)
            );

            CREATE TABLE IF NOT EXISTS dsp_quality_working_hour_exceptions (
                id TEXT PRIMARY KEY,
                revision_id TEXT NOT NULL,
                transporter_external_id TEXT NOT NULL,
                daily_limit_exceeded_raw TEXT,
                daily_limit_exceeded INTEGER,
                weekly_limit_exceeded_raw TEXT,
                weekly_limit_exceeded INTEGER,
                under_offwork_limit_raw TEXT,
                under_offwork_limit INTEGER,
                work_day_limit_exceeded_raw TEXT,
                work_day_limit_exceeded INTEGER,
                wh_exception_raw TEXT,
                wh_exception INTEGER,
                source_page INTEGER,
                source_row TEXT,
                FOREIGN KEY (revision_id) REFERENCES dsp_quality_scorecard_versions(id)
            );

            CREATE TABLE IF NOT EXISTS dsp_quality_focus_areas (
                id TEXT PRIMARY KEY,
                revision_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                metric_key TEXT,
                source_label TEXT NOT NULL,
                source_page INTEGER,
                UNIQUE (revision_id, position),
                FOREIGN KEY (revision_id) REFERENCES dsp_quality_scorecard_versions(id),
                FOREIGN KEY (metric_key) REFERENCES dsp_quality_metric_definitions(metric_key)
            );

            CREATE TABLE IF NOT EXISTS dsp_quality_standard_rules (
                id TEXT PRIMARY KEY,
                standard_set_id TEXT NOT NULL,
                metric_key TEXT NOT NULL,
                target_value TEXT,
                minimum_value TEXT,
                unit TEXT,
                direction TEXT NOT NULL,
                raw_target TEXT,
                raw_minimum TEXT,
                UNIQUE (standard_set_id, metric_key),
                FOREIGN KEY (standard_set_id) REFERENCES dsp_quality_standard_sets(id),
                FOREIGN KEY (metric_key) REFERENCES dsp_quality_metric_definitions(metric_key)
            );

            CREATE INDEX IF NOT EXISTS idx_quality_scorecards_org_period
                ON dsp_quality_scorecards(organization_id, reported_year, reported_week);
            CREATE INDEX IF NOT EXISTS idx_quality_revisions_scorecard
                ON dsp_quality_scorecard_versions(scorecard_id, imported_at);
            CREATE INDEX IF NOT EXISTS idx_quality_transporter_external
                ON dsp_quality_transporter_rows(transporter_external_id, revision_id);
            CREATE INDEX IF NOT EXISTS idx_workforce_external_identity_lookup
                ON workforce_external_identities(organization_id, source, external_id);
            """
        )
        conn.executemany(
            """
            INSERT INTO dsp_quality_metric_definitions (
                metric_key, canonical_label, category, value_type, unit,
                direction, scope, provider, definition_version, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(metric_key) DO NOTHING
            """,
            [
                (
                    item.metric_key,
                    item.canonical_label,
                    item.category,
                    item.value_type.value,
                    item.unit,
                    item.direction.value,
                    item.scope.value,
                    item.provider,
                    item.definition_version,
                    int(item.active),
                )
                for item in METRIC_DEFINITIONS
            ],
        )
