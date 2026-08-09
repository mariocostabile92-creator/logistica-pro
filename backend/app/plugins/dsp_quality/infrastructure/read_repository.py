from app.core.database import db_session


def _dict(row) -> dict | None:
    return {key: row[key] for key in row.keys()} if row else None


def latest_scorecard_overview(organization_id: str) -> dict | None:
    """Return one persisted overview using a fixed, organization-scoped query set."""
    with db_session() as conn:
        main = conn.execute(
            """
            SELECT
                s.id AS scorecard_id,
                s.organization_id,
                s.source_provider,
                s.dsp_identifier,
                s.station,
                s.reported_year,
                s.reported_week,
                s.geography,
                s.active_revision_id AS requested_active_revision_id,
                r.id AS revision_id,
                r.source_filename,
                r.detected_template_version,
                r.imported_at,
                r.imported_by,
                r.rank,
                r.rank_wow_declared,
                r.overall_score,
                r.overall_standing,
                r.standard_set_id,
                ss.provider AS standard_provider,
                ss.detected_source_version AS standard_version,
                ss.effective_from AS standard_effective_from,
                ss.effective_to AS standard_effective_to
            FROM dsp_quality_scorecards s
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
            LEFT JOIN dsp_quality_standard_sets ss
              ON ss.id = r.standard_set_id
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
        if not main:
            return None

        revision_id = main["revision_id"]
        sections = conn.execute(
            """
            SELECT section_key, section_label, standing
            FROM dsp_quality_section_standings
            WHERE revision_id = ?
            ORDER BY section_key
            """,
            (revision_id,),
        ).fetchall()
        focus_areas = conn.execute(
            """
            SELECT position, metric_key, source_label
            FROM dsp_quality_focus_areas
            WHERE revision_id = ?
            ORDER BY position, id
            """,
            (revision_id,),
        ).fetchall()
        counts = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM dsp_quality_metric_observations
               WHERE revision_id = ?) AS dsp_metrics,
              (SELECT COUNT(*) FROM dsp_quality_transporter_rows
               WHERE revision_id = ?) AS transporter_rows,
              (SELECT COUNT(*) FROM dsp_quality_working_hour_exceptions
               WHERE revision_id = ?) AS working_hour_exceptions,
              (SELECT COUNT(*) FROM dsp_quality_transporter_rows
               WHERE revision_id = ? AND mapping_status = 'MATCHED') AS mapped_transporters,
              (SELECT COUNT(*) FROM dsp_quality_transporter_rows
               WHERE revision_id = ? AND mapping_status = 'UNMAPPED') AS unmapped_transporters,
              (SELECT COUNT(*) FROM dsp_quality_transporter_rows
               WHERE revision_id = ? AND mapping_status = 'AMBIGUOUS') AS ambiguous_transporters
            """,
            (revision_id, revision_id, revision_id, revision_id, revision_id, revision_id),
        ).fetchone()

    main_data = _dict(main)
    return {
        "main": main_data,
        "sections": [_dict(row) for row in sections],
        "focus_areas": [_dict(row) for row in focus_areas],
        "counts": _dict(counts),
        "used_fallback": (
            not main_data["requested_active_revision_id"]
            or main_data["requested_active_revision_id"] != main_data["revision_id"]
        ),
    }
