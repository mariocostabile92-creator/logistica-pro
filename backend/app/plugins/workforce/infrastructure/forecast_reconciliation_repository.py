import json
from collections.abc import Sequence

from app.core.database import db_session
from app.plugins.workforce.domain.coverage import (
    CoverageSource,
    ForecastAuthorityStatus,
    ImportedDailyCoverageRequirement,
)
from app.utils.date_utils import utc_now_iso


def _station_key(value: str | None) -> str:
    return str(value or "").strip().casefold()


def _segment_key(value: str | None) -> str:
    return str(value or "").strip().upper()


def _logical_key(item: ImportedDailyCoverageRequirement) -> tuple[str, str, str, str]:
    return (
        item.operational_date,
        _station_key(item.station),
        item.operational_cycle,
        _segment_key(item.coverage_segment),
    )


def matching_rows(
    organization_id: str,
    source_identity: str,
    requirements: Sequence[ImportedDailyCoverageRequirement],
) -> dict[tuple[str, str, str, str], dict[str, object]]:
    if not requirements:
        return {}
    dates = sorted({item.operational_date for item in requirements})
    expected = {_logical_key(item) for item in requirements}
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT id, operational_date, station_key, operational_cycle,
                   coverage_segment, forecast_routes, source, source_identity,
                   source_reference, authority_status, detection_reason,
                   updated_at
            FROM workforce_daily_coverage_requirements
            WHERE organization_id = ?
              AND operational_date >= ? AND operational_date <= ?
              AND source = ? AND source_identity = ?
            """,
            (
                organization_id,
                dates[0],
                dates[-1],
                CoverageSource.LEGACY_IMPORT_BACKFILL.value,
                source_identity,
            ),
        ).fetchall()
    result = {}
    for row in rows:
        key = (
            row["operational_date"],
            row["station_key"],
            row["operational_cycle"],
            row["coverage_segment"],
        )
        if key in expected:
            result[key] = {name: row[name] for name in row.keys()}
    return result


def manual_override_rows(
    organization_id: str,
    requirements: Sequence[ImportedDailyCoverageRequirement],
) -> dict[tuple[str, str, str, str], dict[str, object]]:
    if not requirements:
        return {}
    dates = sorted({item.operational_date for item in requirements})
    expected = {_logical_key(item) for item in requirements}
    manual_sources = (
        CoverageSource.MANUAL_PLANNING_INPUT.value,
        CoverageSource.MANUAL.value,
    )
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT id, operational_date, station_key, operational_cycle,
                   coverage_segment, forecast_routes, source, source_identity,
                   source_reference, updated_at
            FROM workforce_daily_coverage_requirements
            WHERE organization_id = ?
              AND operational_date >= ? AND operational_date <= ?
              AND source IN (?, ?)
            """,
            (organization_id, dates[0], dates[-1], *manual_sources),
        ).fetchall()
    result = {}
    for row in rows:
        key = (
            row["operational_date"],
            row["station_key"],
            row["operational_cycle"],
            row["coverage_segment"],
        )
        if key in expected:
            result[key] = {name: row[name] for name in row.keys()}
    return result


def manual_override_keys(
    organization_id: str,
    requirements: Sequence[ImportedDailyCoverageRequirement],
) -> set[tuple[str, str, str, str]]:
    return set(manual_override_rows(organization_id, requirements))


def _update_rows(conn, rows: list[tuple[object, ...]]) -> None:
    conn.executemany(
        """
        UPDATE workforce_daily_coverage_requirements
        SET authority_status = ?, detection_reason = ?, updated_at = ?
        WHERE id = ? AND organization_id = ?
          AND source = ? AND source_identity = ?
        """,
        rows,
    )


def apply_rejected(
    organization_id: str,
    *,
    source_identity: str,
    requirements: Sequence[ImportedDailyCoverageRequirement],
    actor: str,
    preview_fingerprint: str,
    workforce_import_id: int,
    manual_overrides_preserved: int,
) -> tuple[int, int]:
    if not requirements:
        return 0, 0
    expected = {_logical_key(item): item for item in requirements}
    dates = sorted({item.operational_date for item in requirements})
    now = utc_now_iso()
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT id, operational_date, station_key, operational_cycle,
                   coverage_segment, authority_status, detection_reason
            FROM workforce_daily_coverage_requirements
            WHERE organization_id = ?
              AND operational_date >= ? AND operational_date <= ?
              AND source = ? AND source_identity = ?
            """,
            (
                organization_id,
                dates[0],
                dates[-1],
                CoverageSource.LEGACY_IMPORT_BACKFILL.value,
                source_identity,
            ),
        ).fetchall()
        matched = []
        updates = []
        for row in rows:
            key = (
                row["operational_date"],
                row["station_key"],
                row["operational_cycle"],
                row["coverage_segment"],
            )
            requirement = expected.get(key)
            if requirement is None:
                continue
            matched.append(row)
            if (
                row["authority_status"]
                == ForecastAuthorityStatus.REJECTED_TEMPLATE.value
                and row["detection_reason"] == requirement.detection_reason
            ):
                continue
            updates.append((
                ForecastAuthorityStatus.REJECTED_TEMPLATE.value,
                requirement.detection_reason,
                now,
                int(row["id"]),
                organization_id,
                CoverageSource.LEGACY_IMPORT_BACKFILL.value,
                source_identity,
            ))
        if updates:
            _update_rows(conn, updates)
            conn.execute(
                """
                INSERT INTO workforce_changes (
                    entity_type, entity_id, actor, timestamp, before_value,
                    after_value, reason, source, organization_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "daily_coverage_reconciliation",
                    workforce_import_id,
                    actor,
                    now,
                    None,
                    json.dumps(
                        {
                            "workforce_import_id": workforce_import_id,
                            "source_identity": source_identity,
                            "affected_count": len(matched),
                            "rejected_count": len(updates),
                            "manual_overrides_preserved": manual_overrides_preserved,
                            "preview_fingerprint": preview_fingerprint,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "forecast_template_reconciled",
                    "workforce_maintenance",
                    organization_id,
                ),
            )
    return len(updates), len(matched) - len(updates)


def audit_preview(
    organization_id: str,
    *,
    actor: str,
    after: dict[str, object],
) -> None:
    now = utc_now_iso()
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO workforce_changes (
                entity_type, entity_id, actor, timestamp, before_value,
                after_value, reason, source, organization_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "daily_coverage_reconciliation",
                0,
                actor,
                now,
                None,
                json.dumps(after, ensure_ascii=False, sort_keys=True),
                "forecast_template_reconciliation_preview",
                "workforce_maintenance",
                organization_id,
            ),
        )
