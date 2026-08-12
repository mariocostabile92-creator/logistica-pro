from app.core.database import db_session
from app.plugins.dsp_quality.infrastructure.drivers_repository import (
    TRANSPORTER_METRIC_KEYS,
    _REVISION_JOIN,
)


def _dict(row) -> dict | None:
    return {key: row[key] for key in row.keys()} if row else None


def driver_history_snapshot(
    organization_id: str,
    transporter_external_id: str,
    *,
    scorecard_id: str | None = None,
    limit: int = 52,
) -> dict | None:
    """Load one Transporter history with three fixed-size batch queries."""
    selected_clause = "AND s.id = ?" if scorecard_id else ""
    parameters = (
        (organization_id, scorecard_id)
        if scorecard_id
        else (organization_id,)
    )
    with db_session() as conn:
        anchor = conn.execute(
            f"""
            SELECT
              s.id AS scorecard_id,
              s.source_provider,
              s.dsp_identifier,
              s.station,
              s.reported_year,
              s.reported_week,
              r.id AS revision_id
            FROM dsp_quality_scorecards s
            {_REVISION_JOIN}
            WHERE s.organization_id = ?
              {selected_clause}
            ORDER BY s.reported_year DESC, s.reported_week DESC,
              r.imported_at DESC, s.id DESC
            LIMIT 1
            """,
            parameters,
        ).fetchone()
        if not anchor:
            return None

        periods = conn.execute(
            f"""
            SELECT
              s.id AS scorecard_id,
              s.reported_year,
              s.reported_week,
              r.id AS revision_id,
              r.imported_at,
              r.source_filename,
              t.id AS row_id,
              t.row_index,
              t.transporter_external_id,
              COALESCE(identity_map.status, 'UNMAPPED')
                AS resolved_mapping_status,
              CASE WHEN identity_map.status = 'MATCHED' THEN member.id END
                AS resolved_workforce_member_id,
              CASE WHEN identity_map.status = 'MATCHED' THEN member.display_name END
                AS workforce_display_name
            FROM dsp_quality_scorecards s
            {_REVISION_JOIN}
            JOIN dsp_quality_transporter_rows t
              ON t.revision_id = r.id
             AND t.transporter_external_id = ?
            LEFT JOIN workforce_external_identities identity_map
              ON identity_map.organization_id = s.organization_id
             AND identity_map.source = 'amazon_transporter'
             AND identity_map.external_id = t.transporter_external_id
            LEFT JOIN workforce_members member
              ON member.id = identity_map.workforce_member_id
             AND member.organization_id = s.organization_id
            WHERE s.organization_id = ?
              AND s.source_provider = ?
              AND s.dsp_identifier = ?
              AND s.station = ?
            ORDER BY s.reported_year DESC, s.reported_week DESC,
              r.imported_at DESC, s.id DESC
            LIMIT ?
            """,
            (
                transporter_external_id,
                organization_id,
                anchor["source_provider"],
                anchor["dsp_identifier"],
                anchor["station"],
                limit,
            ),
        ).fetchall()
        period_rows = [_dict(row) for row in periods]
        if not period_rows:
            return {
                "anchor": _dict(anchor),
                "periods": [],
                "observations": [],
            }

        row_ids = [row["row_id"] for row in period_rows]
        row_placeholders = ",".join("?" for _ in row_ids)
        metric_placeholders = ",".join("?" for _ in TRANSPORTER_METRIC_KEYS)
        observations = conn.execute(
            f"""
            SELECT
              observation.transporter_row_id AS row_id,
              observation.metric_key,
              definition.canonical_label,
              definition.value_type,
              definition.unit,
              definition.direction,
              observation.raw_value,
              observation.normalized_numeric_value,
              observation.normalized_text_value,
              observation.value_state
            FROM dsp_quality_transporter_observations observation
            LEFT JOIN dsp_quality_metric_definitions definition
              ON definition.metric_key = observation.metric_key
            WHERE observation.transporter_row_id IN ({row_placeholders})
              AND observation.metric_key IN ({metric_placeholders})
            ORDER BY observation.transporter_row_id, observation.metric_key
            """,
            (*row_ids, *TRANSPORTER_METRIC_KEYS),
        ).fetchall()

    return {
        "anchor": _dict(anchor),
        "periods": period_rows,
        "observations": [_dict(row) for row in observations],
    }
