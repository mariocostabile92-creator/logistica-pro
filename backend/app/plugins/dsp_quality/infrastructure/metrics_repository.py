from app.core.database import db_session


def _dict(row) -> dict | None:
    return {key: row[key] for key in row.keys()} if row else None


_REVISION_JOIN = """
JOIN dsp_quality_scorecard_versions r
  ON r.id = COALESCE(
    (
      SELECT active_revision.id
      FROM dsp_quality_scorecard_versions active_revision
      WHERE active_revision.id = s.active_revision_id
        AND active_revision.scorecard_id = s.id
        AND active_revision.organization_id = s.organization_id
      LIMIT 1
    ),
    (
      SELECT fallback_revision.id
      FROM dsp_quality_scorecard_versions fallback_revision
      WHERE fallback_revision.scorecard_id = s.id
        AND fallback_revision.organization_id = s.organization_id
      ORDER BY
        fallback_revision.active DESC,
        CASE WHEN fallback_revision.status = 'active' THEN 0 ELSE 1 END,
        fallback_revision.imported_at DESC,
        fallback_revision.id DESC
      LIMIT 1
    )
  )
"""


def _metric_rows(conn, revision_id: str | None) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
          d.metric_key,
          d.canonical_label,
          d.category,
          d.value_type,
          d.unit,
          d.direction,
          o.raw_value,
          o.normalized_numeric_value,
          o.normalized_text_value,
          o.value_state,
          o.rating,
          o.compliance_state,
          sr.target_value,
          sr.minimum_value,
          sr.raw_target,
          sr.raw_minimum,
          sr.direction AS standard_direction,
          ss.id AS standard_set_id,
          ss.provider AS standard_provider,
          ss.detected_source_version AS standard_version,
          ss.effective_from AS standard_effective_from,
          ss.effective_to AS standard_effective_to
        FROM dsp_quality_metric_observations o
        JOIN dsp_quality_metric_definitions d ON d.metric_key = o.metric_key
        JOIN dsp_quality_scorecard_versions r ON r.id = o.revision_id
        LEFT JOIN dsp_quality_standard_rules sr
          ON sr.standard_set_id = r.standard_set_id
         AND sr.metric_key = o.metric_key
        LEFT JOIN dsp_quality_standard_sets ss ON ss.id = r.standard_set_id
        WHERE o.revision_id = ?
        ORDER BY d.category, d.canonical_label, d.metric_key
        """,
        (revision_id,),
    ).fetchall()
    return [_dict(row) for row in rows]


def latest_metrics_snapshot(organization_id: str) -> dict | None:
    """Load current and comparable previous DSP metrics with four batch queries."""
    with db_session() as conn:
        current = conn.execute(
            f"""
            SELECT
              s.id AS scorecard_id,
              s.organization_id,
              s.source_provider,
              s.dsp_identifier,
              s.station,
              s.reported_year,
              s.reported_week,
              s.active_revision_id AS requested_active_revision_id,
              r.id AS revision_id,
              r.imported_at
            FROM dsp_quality_scorecards s
            {_REVISION_JOIN}
            WHERE s.organization_id = ?
            ORDER BY
              s.reported_year DESC,
              s.reported_week DESC,
              r.imported_at DESC,
              s.id DESC
            LIMIT 1
            """,
            (organization_id,),
        ).fetchone()
        if not current:
            return None

        previous = conn.execute(
            f"""
            SELECT
              s.id AS scorecard_id,
              s.reported_year,
              s.reported_week,
              r.id AS revision_id,
              r.imported_at
            FROM dsp_quality_scorecards s
            {_REVISION_JOIN}
            WHERE s.organization_id = ?
              AND s.source_provider = ?
              AND s.dsp_identifier = ?
              AND s.station = ?
              AND (
                s.reported_year < ?
                OR (s.reported_year = ? AND s.reported_week < ?)
              )
            ORDER BY
              s.reported_year DESC,
              s.reported_week DESC,
              r.imported_at DESC,
              s.id DESC
            LIMIT 1
            """,
            (
                organization_id,
                current["source_provider"],
                current["dsp_identifier"],
                current["station"],
                current["reported_year"],
                current["reported_year"],
                current["reported_week"],
            ),
        ).fetchone()

        current_metrics = _metric_rows(conn, current["revision_id"])
        previous_metrics = _metric_rows(
            conn,
            previous["revision_id"] if previous else None,
        )

    current_data = _dict(current)
    return {
        "current": current_data,
        "previous": _dict(previous),
        "current_metrics": current_metrics,
        "previous_metrics": previous_metrics,
        "used_fallback": (
            not current_data["requested_active_revision_id"]
            or current_data["requested_active_revision_id"] != current_data["revision_id"]
        ),
    }

