from app.core.database import db_session


TRANSPORTER_METRIC_KEYS = (
    "delivered",
    "delivery_completion_rate",
    "delivery_success_conditions_dpmo",
    "lost_on_road_dpmo",
    "photo_on_delivery",
    "contact_compliance",
    "customer_escalations_count",
    "customer_delivery_feedback_dpmo",
)


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


def _transporter_rows(conn, revision_id: str, organization_id: str) -> list[dict]:
    placeholders = ",".join("?" for _ in TRANSPORTER_METRIC_KEYS)
    rows = conn.execute(
        f"""
        SELECT
          t.id AS row_id,
          t.row_index,
          t.transporter_external_id,
          COALESCE(identity_map.status, 'UNMAPPED') AS resolved_mapping_status,
          CASE WHEN identity_map.status = 'MATCHED' THEN member.id END
            AS resolved_workforce_member_id,
          CASE WHEN identity_map.status = 'MATCHED' THEN member.display_name END
            AS workforce_display_name,
          observation.metric_key,
          definition.canonical_label,
          definition.value_type,
          definition.unit,
          definition.direction,
          observation.raw_value,
          observation.normalized_numeric_value,
          observation.normalized_text_value,
          observation.value_state
        FROM dsp_quality_transporter_rows t
        JOIN dsp_quality_scorecard_versions revision
          ON revision.id = t.revision_id
         AND revision.organization_id = ?
        LEFT JOIN dsp_quality_transporter_observations observation
          ON observation.transporter_row_id = t.id
         AND observation.metric_key IN ({placeholders})
        LEFT JOIN dsp_quality_metric_definitions definition
          ON definition.metric_key = observation.metric_key
        LEFT JOIN workforce_external_identities identity_map
          ON identity_map.organization_id = revision.organization_id
         AND identity_map.source = 'amazon_transporter'
         AND identity_map.external_id = t.transporter_external_id
        LEFT JOIN workforce_members member
          ON member.id = identity_map.workforce_member_id
         AND member.organization_id = revision.organization_id
        WHERE t.revision_id = ?
        ORDER BY t.row_index, observation.metric_key
        """,
        (organization_id, *TRANSPORTER_METRIC_KEYS, revision_id),
    ).fetchall()
    return [_dict(row) for row in rows]


def latest_drivers_snapshot(organization_id: str) -> dict | None:
    """Load current and previous Transporter performance in four batch queries."""
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

        current_rows = _transporter_rows(
            conn, current["revision_id"], organization_id,
        )
        previous_rows = _transporter_rows(
            conn, previous["revision_id"], organization_id,
        ) if previous else []

    current_data = _dict(current)
    return {
        "current": current_data,
        "previous": _dict(previous),
        "current_rows": current_rows,
        "previous_rows": previous_rows,
        "used_fallback": (
            not current_data["requested_active_revision_id"]
            or current_data["requested_active_revision_id"] != current_data["revision_id"]
        ),
    }
