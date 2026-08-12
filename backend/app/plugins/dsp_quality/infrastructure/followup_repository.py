import json
import uuid

from app.core.database import db_session
from app.plugins.dsp_quality.infrastructure.drivers_repository import _REVISION_JOIN
from app.utils.date_utils import utc_now_iso


ACTIVE_STATUSES = ("OPEN", "REVIEW_DUE", "IMPROVED", "UNCHANGED", "WORSENED")


def _dict(row) -> dict | None:
    return {key: row[key] for key in row.keys()} if row else None


def baseline_snapshot(
    organization_id: str,
    scorecard_id: str,
    transporter_external_id: str,
    metric_key: str,
) -> dict | None:
    with db_session() as conn:
        row = conn.execute(
            f"""
            SELECT
              s.id AS scorecard_id,
              s.source_provider,
              s.dsp_identifier,
              s.station,
              s.reported_year,
              s.reported_week,
              t.workforce_member_id AS imported_workforce_member_id,
              CASE WHEN identity_map.status = 'MATCHED'
                THEN identity_map.workforce_member_id END AS workforce_member_id,
              observation.normalized_numeric_value,
              observation.value_state,
              definition.canonical_label,
              definition.unit,
              definition.direction,
              definition.scope
            FROM dsp_quality_scorecards s
            {_REVISION_JOIN}
            JOIN dsp_quality_transporter_rows t
              ON t.revision_id = r.id
             AND t.transporter_external_id = ?
            LEFT JOIN dsp_quality_transporter_observations observation
              ON observation.transporter_row_id = t.id
             AND observation.metric_key = ?
            LEFT JOIN dsp_quality_metric_definitions definition
              ON definition.metric_key = ?
            LEFT JOIN workforce_external_identities identity_map
              ON identity_map.organization_id = s.organization_id
             AND identity_map.source = 'amazon_transporter'
             AND identity_map.external_id = t.transporter_external_id
            WHERE s.organization_id = ? AND s.id = ?
            LIMIT 1
            """,
            (
                transporter_external_id,
                metric_key,
                metric_key,
                organization_id,
                scorecard_id,
            ),
        ).fetchone()
    return _dict(row)


def find_active_duplicate(
    organization_id: str,
    transporter_external_id: str,
    metric_key: str,
    scorecard_id: str,
) -> dict | None:
    placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
    with db_session() as conn:
        row = conn.execute(
            f"""
            SELECT id FROM dsp_quality_followups
            WHERE organization_id = ?
              AND transporter_external_id = ?
              AND metric_key = ?
              AND created_from_scorecard_id = ?
              AND status IN ({placeholders})
            LIMIT 1
            """,
            (
                organization_id,
                transporter_external_id,
                metric_key,
                scorecard_id,
                *ACTIVE_STATUSES,
            ),
        ).fetchone()
    return _dict(row)


def create_followup(values: dict, actor: str) -> str | None:
    followup_id = str(uuid.uuid4())
    now = utc_now_iso()
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO dsp_quality_followups (
              id, organization_id, transporter_external_id,
              workforce_member_id, created_from_scorecard_id,
              created_from_week, created_from_year, metric_key,
              baseline_value, baseline_direction, baseline_status,
              note, status, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)
            ON CONFLICT DO NOTHING
            """,
            (
                followup_id,
                values["organization_id"],
                values["transporter_external_id"],
                values.get("workforce_member_id"),
                values["created_from_scorecard_id"],
                values["created_from_week"],
                values["created_from_year"],
                values["metric_key"],
                values["baseline_value"],
                values["baseline_direction"],
                values["baseline_status"],
                values["note"],
                actor,
                now,
            ),
        )
        if cursor.rowcount != 1:
            return None
        _insert_event(
            conn,
            followup_id=followup_id,
            organization_id=values["organization_id"],
            event_type="quality_followup_created",
            actor=actor,
            transporter_external_id=values["transporter_external_id"],
            metric_key=values["metric_key"],
            scorecard_id=values["created_from_scorecard_id"],
            details={"status": "OPEN"},
            created_at=now,
        )
    return followup_id


def _insert_event(
    conn,
    *,
    followup_id: str,
    organization_id: str,
    event_type: str,
    actor: str,
    transporter_external_id: str,
    metric_key: str,
    scorecard_id: str | None,
    details: dict,
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO dsp_quality_followup_events (
          id, followup_id, organization_id, event_type, actor,
          transporter_external_id, metric_key, scorecard_id,
          details, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            followup_id,
            organization_id,
            event_type,
            actor,
            transporter_external_id,
            metric_key,
            scorecard_id,
            json.dumps(details, sort_keys=True),
            created_at,
        ),
    )


def followup_snapshot(
    organization_id: str,
    *,
    followup_id: str | None = None,
    transporter_external_id: str | None = None,
    metric_key: str | None = None,
) -> dict:
    clauses = ["followup.organization_id = ?"]
    parameters: list[object] = [organization_id]
    if followup_id:
        clauses.append("followup.id = ?")
        parameters.append(followup_id)
    if transporter_external_id:
        clauses.append("followup.transporter_external_id = ?")
        parameters.append(transporter_external_id)
    if metric_key:
        clauses.append("followup.metric_key = ?")
        parameters.append(metric_key)
    with db_session() as conn:
        followups = conn.execute(
            f"""
            SELECT
              followup.*,
              baseline.source_provider,
              baseline.dsp_identifier,
              baseline.station,
              definition.canonical_label AS metric_label,
              definition.unit AS metric_unit,
              COALESCE(member.display_name,
                followup.transporter_external_id) AS driver_display_name
            FROM dsp_quality_followups followup
            JOIN dsp_quality_scorecards baseline
              ON baseline.id = followup.created_from_scorecard_id
             AND baseline.organization_id = followup.organization_id
            JOIN dsp_quality_metric_definitions definition
              ON definition.metric_key = followup.metric_key
            LEFT JOIN workforce_members member
              ON member.id = followup.workforce_member_id
             AND member.organization_id = followup.organization_id
            WHERE {' AND '.join(clauses)}
            ORDER BY followup.created_at DESC, followup.id DESC
            """,
            tuple(parameters),
        ).fetchall()
        rows = [_dict(row) for row in followups]
        if not rows:
            return {"followups": [], "scorecards": [], "observations": []}

        scorecards = conn.execute(
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
            ORDER BY s.reported_year, s.reported_week, s.id
            """,
            (organization_id,),
        ).fetchall()

        transporter_ids = sorted({row["transporter_external_id"] for row in rows})
        metric_keys = sorted({row["metric_key"] for row in rows})
        transporter_placeholders = ",".join("?" for _ in transporter_ids)
        metric_placeholders = ",".join("?" for _ in metric_keys)
        observations = conn.execute(
            f"""
            SELECT
              s.id AS scorecard_id,
              t.transporter_external_id,
              t.id AS row_id,
              observation.metric_key,
              observation.normalized_numeric_value,
              observation.value_state
            FROM dsp_quality_scorecards s
            {_REVISION_JOIN}
            JOIN dsp_quality_transporter_rows t ON t.revision_id = r.id
            LEFT JOIN dsp_quality_transporter_observations observation
              ON observation.transporter_row_id = t.id
             AND observation.metric_key IN ({metric_placeholders})
            WHERE s.organization_id = ?
              AND t.transporter_external_id IN ({transporter_placeholders})
            ORDER BY s.reported_year, s.reported_week, s.id
            """,
            (*metric_keys, organization_id, *transporter_ids),
        ).fetchall()
    return {
        "followups": rows,
        "scorecards": [_dict(row) for row in scorecards],
        "observations": [_dict(row) for row in observations],
    }


def apply_review_updates(updates: list[dict]) -> None:
    if not updates:
        return
    now = utc_now_iso()
    with db_session() as conn:
        for update in updates:
            if update.get("result"):
                cursor = conn.execute(
                    """
                    UPDATE dsp_quality_followups
                    SET target_review_scorecard_id = ?, reviewed_at = ?,
                        review_result = ?, status = ?
                    WHERE id = ? AND organization_id = ?
                      AND status IN ('OPEN', 'REVIEW_DUE')
                      AND review_result IS NULL
                    """,
                    (
                        update["scorecard_id"],
                        now,
                        update["result"],
                        update["result"],
                        update["id"],
                        update["organization_id"],
                    ),
                )
                if cursor.rowcount == 1:
                    _insert_event(
                        conn,
                        followup_id=update["id"],
                        organization_id=update["organization_id"],
                        event_type="quality_followup_reviewed",
                        actor="system:quality-followup-review",
                        transporter_external_id=update["transporter_external_id"],
                        metric_key=update["metric_key"],
                        scorecard_id=update["scorecard_id"],
                        details={"result": update["result"]},
                        created_at=now,
                    )
            elif not update.get("target_already_set"):
                conn.execute(
                    """
                    UPDATE dsp_quality_followups
                    SET target_review_scorecard_id = ?
                    WHERE id = ? AND organization_id = ?
                      AND target_review_scorecard_id IS NULL
                      AND status = 'OPEN'
                    """,
                    (
                        update["scorecard_id"],
                        update["id"],
                        update["organization_id"],
                    ),
                )


def close_followup(
    organization_id: str,
    followup_id: str,
    *,
    actor: str,
    note: str | None,
) -> None:
    now = utc_now_iso()
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT * FROM dsp_quality_followups
            WHERE id = ? AND organization_id = ?
            """,
            (followup_id, organization_id),
        ).fetchone()
        if not row:
            raise LookupError("Follow-up Quality non trovato.")
        if row["status"] == "CLOSED":
            raise RuntimeError("Il follow-up Quality è già chiuso.")
        if row["review_result"] is None:
            raise RuntimeError("Il follow-up può essere chiuso dopo una verifica comparabile.")
        conn.execute(
            """
            UPDATE dsp_quality_followups
            SET status = 'CLOSED', closed_at = ?, closed_by = ?, close_note = ?
            WHERE id = ? AND organization_id = ?
            """,
            (now, actor, note, followup_id, organization_id),
        )
        _insert_event(
            conn,
            followup_id=followup_id,
            organization_id=organization_id,
            event_type="quality_followup_closed",
            actor=actor,
            transporter_external_id=row["transporter_external_id"],
            metric_key=row["metric_key"],
            scorecard_id=row["target_review_scorecard_id"],
            details={"review_result": row["review_result"]},
            created_at=now,
        )


def list_events(organization_id: str, followup_id: str) -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT * FROM dsp_quality_followup_events
            WHERE organization_id = ? AND followup_id = ?
            ORDER BY created_at,
              CASE event_type
                WHEN 'quality_followup_created' THEN 1
                WHEN 'quality_followup_reviewed' THEN 2
                WHEN 'quality_followup_closed' THEN 3
                ELSE 4
              END,
              id
            """,
            (organization_id, followup_id),
        ).fetchall()
    return [_dict(row) for row in rows]
