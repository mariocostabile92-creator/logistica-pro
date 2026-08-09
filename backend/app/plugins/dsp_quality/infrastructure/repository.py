import hashlib
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.core.database import db_session
from app.plugins.dsp_quality.application.import_contract import QualityImportDocument
from app.plugins.dsp_quality.domain.models import (
    NormalizedQualityValue,
    QualityMappingStatus,
)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _id() -> str:
    return str(uuid.uuid4())


def _attachment_entity_id(scorecard_id: str) -> int:
    # The Attachment Engine uses numeric entity ids. Keep this deterministic
    # surrogate inside PostgreSQL's positive signed BIGINT range.
    value = int.from_bytes(hashlib.sha256(scorecard_id.encode("utf-8")).digest()[:8], "big")
    return (value & ((1 << 63) - 1)) or 1


def _dict(row) -> dict | None:
    return {key: row[key] for key in row.keys()} if row else None


def _raw(value: object) -> str | None:
    return None if value is None else str(value)


def _decimal(value: object) -> str | None:
    return None if value is None else str(Decimal(str(value).removesuffix("%")))


def _value_columns(value: NormalizedQualityValue) -> tuple[object, ...]:
    return (
        value.raw_value,
        _decimal(value.normalized_numeric_value),
        value.normalized_text_value,
        value.value_state.value,
        value.rating,
        value.compliance_state,
        value.normalization_rule_version,
    )


def metric_definitions() -> dict[str, dict]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM dsp_quality_metric_definitions WHERE active = 1"
        ).fetchall()
    return {row["metric_key"]: _dict(row) for row in rows}


def metric_definition_count() -> int:
    with db_session() as conn:
        row = conn.execute(
            "SELECT COUNT(*) count FROM dsp_quality_metric_definitions"
        ).fetchone()
    return int(row["count"])


def find_external_identity(
    organization_id: str,
    source: str,
    external_id: str,
) -> dict | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT * FROM workforce_external_identities
            WHERE organization_id = ? AND source = ? AND external_id = ?
            """,
            (organization_id, source, external_id),
        ).fetchone()
    return _dict(row)


def mapping_snapshots(organization_id: str, external_ids: list[str]) -> dict[str, dict]:
    identifiers = sorted({item.strip() for item in external_ids if item.strip()})
    if not identifiers:
        return {}
    placeholders = ",".join("?" for _ in identifiers)
    with db_session() as conn:
        rows = conn.execute(
            f"""
            SELECT external_id, status, workforce_member_id
            FROM workforce_external_identities
            WHERE organization_id = ? AND source = 'amazon_transporter'
              AND external_id IN ({placeholders})
            """,
            (organization_id, *identifiers),
        ).fetchall()
    return {row["external_id"]: _dict(row) for row in rows}  # type: ignore[misc]


def inspect_import_action(
    *,
    organization_id: str,
    source_fingerprint: str,
    source_provider: str,
    dsp_identifier: str,
    station: str,
    reported_year: int,
    reported_week: int,
) -> dict:
    with db_session() as conn:
        revision = conn.execute(
            """
            SELECT id, scorecard_id FROM dsp_quality_scorecard_versions
            WHERE organization_id = ? AND source_fingerprint_sha256 = ?
            """,
            (organization_id, source_fingerprint),
        ).fetchone()
        if revision:
            return {
                "action": "NO_OP",
                "existing_scorecard": revision["scorecard_id"],
                "existing_revision": revision["id"],
            }
        scorecard = conn.execute(
            """
            SELECT id, active_revision_id FROM dsp_quality_scorecards
            WHERE organization_id = ? AND source_provider = ?
              AND dsp_identifier = ? AND station = ?
              AND reported_year = ? AND reported_week = ?
            """,
            (
                organization_id,
                source_provider,
                dsp_identifier,
                station,
                reported_year,
                reported_week,
            ),
        ).fetchone()
    if scorecard:
        return {
            "action": "NEW_REVISION",
            "existing_scorecard": scorecard["id"],
            "existing_revision": scorecard["active_revision_id"],
        }
    return {
        "action": "CREATE",
        "existing_scorecard": None,
        "existing_revision": None,
    }


def save_external_identity(
    *,
    organization_id: str,
    source: str,
    external_id: str,
    status: QualityMappingStatus,
    workforce_member_id: int | None,
    actor: str,
    valid_from: str | None = None,
    valid_to: str | None = None,
) -> dict:
    now = utc_now_iso()
    with db_session() as conn:
        if workforce_member_id is not None:
            member = conn.execute(
                """
                SELECT id FROM workforce_members
                WHERE id = ? AND organization_id = ?
                """,
                (workforce_member_id, organization_id),
            ).fetchone()
            if not member:
                raise ValueError("Workforce member not found in organization.")
        existing = conn.execute(
            """
            SELECT * FROM workforce_external_identities
            WHERE organization_id = ? AND source = ? AND external_id = ?
            """,
            (organization_id, source, external_id),
        ).fetchone()
        identity_id = existing["id"] if existing else _id()
        created_at = existing["created_at"] if existing else now
        conn.execute(
            """
            INSERT INTO workforce_external_identities (
                id, organization_id, source, external_id, workforce_member_id,
                status, valid_from, valid_to, verified_by, verified_at,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(organization_id, source, external_id) DO UPDATE SET
                workforce_member_id=excluded.workforce_member_id,
                status=excluded.status,
                valid_from=excluded.valid_from,
                valid_to=excluded.valid_to,
                verified_by=excluded.verified_by,
                verified_at=excluded.verified_at,
                updated_at=excluded.updated_at
            """,
            (
                identity_id,
                organization_id,
                source,
                external_id,
                workforce_member_id,
                status.value,
                valid_from,
                valid_to,
                actor,
                now,
                created_at,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO workforce_external_identity_events (
                id, identity_id, organization_id, action, actor, details, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _id(),
                identity_id,
                organization_id,
                "mapped" if status is QualityMappingStatus.MATCHED else "status_set",
                actor,
                json.dumps(
                    {
                        "source": source,
                        "external_id": external_id,
                        "workforce_member_id": workforce_member_id,
                        "status": status.value,
                    },
                    sort_keys=True,
                ),
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM workforce_external_identities WHERE id = ?",
            (identity_id,),
        ).fetchone()
    return _dict(row)  # type: ignore[return-value]


def _mapping_snapshot(conn, organization_id: str, external_id: str) -> tuple[str, int | None]:
    row = conn.execute(
        """
        SELECT status, workforce_member_id
        FROM workforce_external_identities
        WHERE organization_id = ? AND source = 'amazon_transporter'
          AND external_id = ?
        """,
        (organization_id, external_id),
    ).fetchone()
    if not row:
        return QualityMappingStatus.UNMAPPED.value, None
    return str(row["status"]), row["workforce_member_id"]


def persist_import(
    *,
    organization_id: str,
    document: QualityImportDocument,
    source_fingerprint: str,
    imported_by: str,
    dsp_values: dict[str, NormalizedQualityValue],
    transporter_values: list[dict[str, NormalizedQualityValue]],
    working_hour_values: list[dict[str, bool | None]],
) -> dict:
    now = utc_now_iso()
    identity = document.identity
    with db_session() as conn:
        existing_revision = conn.execute(
            """
            SELECT r.*, s.active_revision_id
            FROM dsp_quality_scorecard_versions r
            JOIN dsp_quality_scorecards s ON s.id = r.scorecard_id
            WHERE r.organization_id = ? AND r.source_fingerprint_sha256 = ?
            """,
            (organization_id, source_fingerprint),
        ).fetchone()
        if existing_revision:
            return {
                "scorecard_id": existing_revision["scorecard_id"],
                "revision_id": existing_revision["id"],
                "previous_revision_id": None,
                "active_revision_id": existing_revision["active_revision_id"],
                "revision_created": False,
                "idempotent": True,
            }

        scorecard = conn.execute(
            """
            SELECT * FROM dsp_quality_scorecards
            WHERE organization_id = ? AND source_provider = ?
              AND dsp_identifier = ? AND station = ?
              AND reported_year = ? AND reported_week = ?
            """,
            (
                organization_id,
                identity.source_provider,
                identity.dsp_identifier,
                identity.station,
                identity.reported_year,
                identity.reported_week,
            ),
        ).fetchone()
        scorecard_id = scorecard["id"] if scorecard else _id()
        attachment_entity_id = (
            scorecard["attachment_entity_id"]
            if scorecard and scorecard["attachment_entity_id"] is not None
            else _attachment_entity_id(scorecard_id)
        )
        previous_revision_id = scorecard["active_revision_id"] if scorecard else None
        if not scorecard:
            conn.execute(
                """
                INSERT INTO dsp_quality_scorecards (
                    id, organization_id, source_provider, dsp_identifier,
                    station, reported_year, reported_week, geography,
                    attachment_entity_id, active_revision_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    scorecard_id,
                    organization_id,
                    identity.source_provider,
                    identity.dsp_identifier,
                    identity.station,
                    identity.reported_year,
                    identity.reported_week,
                    identity.geography,
                    attachment_entity_id,
                    now,
                    now,
                ),
            )
        elif scorecard["attachment_entity_id"] is None:
            conn.execute(
                """
                UPDATE dsp_quality_scorecards SET attachment_entity_id = ?
                WHERE id = ? AND organization_id = ?
                """,
                (attachment_entity_id, scorecard_id, organization_id),
            )

        standard_set_id = None
        if document.standards and document.standards.rules:
            standard_set_id = _id()
            standards = document.standards
            conn.execute(
                """
                INSERT INTO dsp_quality_standard_sets (
                    id, provider, geography_scope, station_scope,
                    detected_source_version, effective_from, effective_to,
                    source_fingerprint, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    standard_set_id,
                    standards.provider,
                    standards.geography_scope,
                    standards.station_scope,
                    standards.detected_source_version,
                    standards.effective_from,
                    standards.effective_to,
                    source_fingerprint,
                    now,
                ),
            )
            for rule in standards.rules:
                conn.execute(
                    """
                    INSERT INTO dsp_quality_standard_rules (
                        id, standard_set_id, metric_key, target_value,
                        minimum_value, unit, direction, raw_target, raw_minimum,
                        source_page
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _id(),
                        standard_set_id,
                        rule.metric_key,
                        _decimal(rule.target_value),
                        _decimal(rule.minimum_value),
                        rule.unit,
                        rule.direction.value,
                        rule.raw_target or _raw(rule.target_value),
                        rule.raw_minimum or _raw(rule.minimum_value),
                        rule.source_page,
                    ),
                )

        if previous_revision_id:
            conn.execute(
                """
                UPDATE dsp_quality_scorecard_versions
                SET active = 0, status = 'superseded'
                WHERE id = ? AND organization_id = ?
                """,
                (previous_revision_id, organization_id),
            )

        revision_id = _id()
        revision = document.revision
        conn.execute(
            """
            INSERT INTO dsp_quality_scorecard_versions (
                id, organization_id, scorecard_id, source_filename,
                source_fingerprint_sha256, parser_adapter, parser_version,
                detected_template_version, imported_at, imported_by, status,
                source_attachment_reference, rank, rank_wow_declared,
                overall_score, overall_standing, raw_period_label, active,
                standard_set_id, working_hours_section_present,
                working_hours_exception_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (
                revision_id,
                organization_id,
                scorecard_id,
                revision.source_filename,
                source_fingerprint,
                revision.parser_adapter,
                revision.parser_version,
                revision.detected_template_version,
                now,
                imported_by,
                revision.source_attachment_reference,
                revision.rank,
                revision.rank_wow_declared,
                _decimal(revision.overall_score),
                revision.overall_standing,
                revision.raw_period_label,
                standard_set_id,
                int(document.working_hours.section_present),
                len(document.working_hours.exceptions),
            ),
        )
        conn.execute(
            """
            UPDATE dsp_quality_scorecards
            SET active_revision_id = ?, updated_at = ?, geography = COALESCE(?, geography)
            WHERE id = ? AND organization_id = ?
            """,
            (revision_id, now, identity.geography, scorecard_id, organization_id),
        )

        for metric in document.dsp_metrics:
            value = dsp_values[metric.metric_key]
            conn.execute(
                """
                INSERT INTO dsp_quality_metric_observations (
                    id, revision_id, metric_key, raw_value,
                    normalized_numeric_value, normalized_text_value,
                    value_state, rating, compliance_state,
                    normalization_rule_version, source_page, source_table,
                    source_row, source_column, extracted_label
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _id(), revision_id, metric.metric_key,
                    *_value_columns(value), metric.source_page,
                    metric.source_table, metric.source_row,
                    metric.source_column, metric.extracted_label,
                ),
            )

        for section in document.sections:
            conn.execute(
                """
                INSERT INTO dsp_quality_section_standings (
                    id, revision_id, section_key, section_label, standing, source_page
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (_id(), revision_id, section.section_key, section.section_label, section.standing, section.source_page),
            )

        for index, transporter in enumerate(document.transporter_rows):
            mapping_status, workforce_member_id = _mapping_snapshot(
                conn, organization_id, transporter.transporter_external_id
            )
            row_id = _id()
            row_fingerprint = transporter.raw_row_fingerprint or hashlib.sha256(
                json.dumps(
                    transporter.model_dump(mode="json"),
                    sort_keys=True,
                    ensure_ascii=True,
                ).encode("utf-8")
            ).hexdigest()
            conn.execute(
                """
                INSERT INTO dsp_quality_transporter_rows (
                    id, revision_id, transporter_external_id, row_index,
                    workforce_member_id, mapping_status, source_page,
                    raw_row_fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row_id, revision_id, transporter.transporter_external_id,
                    transporter.row_index, workforce_member_id, mapping_status,
                    transporter.source_page, row_fingerprint,
                ),
            )
            values = transporter_values[index]
            for metric in transporter.metrics:
                value = values[metric.metric_key]
                conn.execute(
                    """
                    INSERT INTO dsp_quality_transporter_observations (
                        id, transporter_row_id, metric_key, raw_value,
                        normalized_numeric_value, normalized_text_value,
                        value_state, rating, compliance_state,
                        normalization_rule_version, source_page, source_column
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _id(), row_id, metric.metric_key,
                        *_value_columns(value), metric.source_page,
                        metric.source_column,
                    ),
                )

        for index, exception in enumerate(document.working_hours.exceptions):
            normalized = working_hour_values[index]
            conn.execute(
                """
                INSERT INTO dsp_quality_working_hour_exceptions (
                    id, revision_id, transporter_external_id,
                    daily_limit_exceeded_raw, daily_limit_exceeded,
                    weekly_limit_exceeded_raw, weekly_limit_exceeded,
                    under_offwork_limit_raw, under_offwork_limit,
                    work_day_limit_exceeded_raw, work_day_limit_exceeded,
                    wh_exception_raw, wh_exception, source_page, source_row
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _id(), revision_id, exception.transporter_external_id,
                    exception.daily_limit_exceeded, normalized["daily_limit_exceeded"],
                    exception.weekly_limit_exceeded, normalized["weekly_limit_exceeded"],
                    exception.under_offwork_limit, normalized["under_offwork_limit"],
                    exception.work_day_limit_exceeded, normalized["work_day_limit_exceeded"],
                    exception.wh_exception, normalized["wh_exception"],
                    exception.source_page, exception.source_row,
                ),
            )

        for focus in document.focus_areas:
            conn.execute(
                """
                INSERT INTO dsp_quality_focus_areas (
                    id, revision_id, position, metric_key, source_label, source_page
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (_id(), revision_id, focus.position, focus.metric_key, focus.source_label, focus.source_page),
            )

    return {
        "scorecard_id": scorecard_id,
        "revision_id": revision_id,
        "previous_revision_id": previous_revision_id,
        "active_revision_id": revision_id,
        "revision_created": True,
        "idempotent": False,
    }


def list_scorecards(organization_id: str) -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM dsp_quality_scorecards WHERE organization_id = ? ORDER BY created_at",
            (organization_id,),
        ).fetchall()
    return [_dict(row) for row in rows]  # type: ignore[misc]


def scorecard_attachment_entity_id(organization_id: str, scorecard_id: str) -> int:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT attachment_entity_id FROM dsp_quality_scorecards
            WHERE id = ? AND organization_id = ?
            """,
            (scorecard_id, organization_id),
        ).fetchone()
        if not row:
            raise ValueError("DSP Quality scorecard not found.")
        entity_id = row["attachment_entity_id"]
        if entity_id is None:
            entity_id = _attachment_entity_id(scorecard_id)
            conn.execute(
                """
                UPDATE dsp_quality_scorecards SET attachment_entity_id = ?
                WHERE id = ? AND organization_id = ?
                """,
                (entity_id, scorecard_id, organization_id),
            )
    return int(entity_id)


def revision_source_attachment_reference(
    organization_id: str,
    revision_id: str,
) -> str | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT source_attachment_reference FROM dsp_quality_scorecard_versions
            WHERE id = ? AND organization_id = ?
            """,
            (revision_id, organization_id),
        ).fetchone()
    if not row:
        raise ValueError("DSP Quality revision not found.")
    return row["source_attachment_reference"]


def set_revision_source_attachment_reference(
    organization_id: str,
    revision_id: str,
    attachment_id: str,
) -> None:
    with db_session() as conn:
        cursor = conn.execute(
            """
            UPDATE dsp_quality_scorecard_versions
            SET source_attachment_reference = ?
            WHERE id = ? AND organization_id = ?
              AND source_attachment_reference IS NULL
            """,
            (attachment_id, revision_id, organization_id),
        )
        if cursor.rowcount != 1:
            row = conn.execute(
                """
                SELECT source_attachment_reference
                FROM dsp_quality_scorecard_versions
                WHERE id = ? AND organization_id = ?
                """,
                (revision_id, organization_id),
            ).fetchone()
            if not row or row["source_attachment_reference"] != attachment_id:
                raise ValueError("DSP Quality attachment link could not be updated.")


def list_revisions(organization_id: str, scorecard_id: str) -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT * FROM dsp_quality_scorecard_versions
            WHERE organization_id = ? AND scorecard_id = ?
            ORDER BY imported_at, id
            """,
            (organization_id, scorecard_id),
        ).fetchall()
    return [_dict(row) for row in rows]  # type: ignore[misc]


def list_metric_observations(revision_id: str) -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM dsp_quality_metric_observations WHERE revision_id = ? ORDER BY metric_key",
            (revision_id,),
        ).fetchall()
    return [_dict(row) for row in rows]  # type: ignore[misc]


def list_transporter_rows(revision_id: str) -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM dsp_quality_transporter_rows WHERE revision_id = ? ORDER BY row_index",
            (revision_id,),
        ).fetchall()
    return [_dict(row) for row in rows]  # type: ignore[misc]
