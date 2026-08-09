from app.core.database import db_session


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
      ORDER BY fallback_revision.active DESC,
        CASE WHEN fallback_revision.status = 'active' THEN 0 ELSE 1 END,
        fallback_revision.imported_at DESC,
        fallback_revision.id DESC
      LIMIT 1
    )
  )
"""


def list_history(organization_id: str) -> list[dict]:
    """Return compact scorecard metadata ordered by operational period."""
    with db_session() as conn:
        rows = conn.execute(
            f"""
            SELECT
              s.id AS scorecard_id,
              r.id AS active_revision_id,
              s.dsp_identifier,
              s.station,
              s.reported_week,
              s.reported_year,
              s.geography,
              r.overall_score,
              r.overall_standing,
              r.rank,
              r.rank_wow_declared,
              r.imported_at,
              r.source_filename,
              (
                SELECT COUNT(*)
                FROM dsp_quality_scorecard_versions revisions
                WHERE revisions.organization_id = s.organization_id
                  AND revisions.scorecard_id = s.id
              ) AS revision_count
            FROM dsp_quality_scorecards s
            {_REVISION_JOIN}
            WHERE s.organization_id = ?
            ORDER BY s.reported_year DESC, s.reported_week DESC,
              s.dsp_identifier, s.station, s.id
            """,
            (organization_id,),
        ).fetchall()
    return [{key: row[key] for key in row.keys()} for row in rows]


def scorecard_exists(organization_id: str, scorecard_id: str) -> bool:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM dsp_quality_scorecards
            WHERE organization_id = ? AND id = ?
            """,
            (organization_id, scorecard_id),
        ).fetchone()
    return bool(row)

