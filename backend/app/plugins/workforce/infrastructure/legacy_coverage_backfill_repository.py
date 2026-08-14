import json
from collections.abc import Sequence
from typing import Any

from app.core.database import db_session
from app.plugins.workforce.domain.coverage import (
    CoverageSource,
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


def _import_record(row) -> dict[str, object]:
    return {
        "workforce_import_id": int(row["id"]),
        "organization_id": row["organization_id"],
        "fingerprint": row["fingerprint"],
        "original_filename": row["original_filename"],
        "imported_at": row["imported_at"],
        "summary": json.loads(row["summary"]),
    }


def _row_dict(row) -> dict[str, object]:
    return {key: row[key] for key in row.keys()}


def find_import(
    organization_id: str,
    *,
    workforce_import_id: int | None = None,
    fingerprint: str | None = None,
) -> dict[str, object] | None:
    conditions = ["organization_id = ?"]
    parameters: list[object] = [organization_id]
    if workforce_import_id is not None:
        conditions.append("id = ?")
        parameters.append(workforce_import_id)
    if fingerprint is not None:
        conditions.append("fingerprint = ?")
        parameters.append(fingerprint)
    with db_session() as conn:
        rows = conn.execute(
            f"""
            SELECT id, organization_id, fingerprint, original_filename,
                   imported_at, summary
            FROM workforce_imports
            WHERE {' AND '.join(conditions)}
            ORDER BY imported_at DESC, id DESC
            """,
            parameters,
        ).fetchall()
    if not rows:
        return None
    if workforce_import_id is not None or fingerprint is not None:
        return _import_record(rows[0])
    for row in rows:
        summary = json.loads(row["summary"])
        if "coverage_requirements_detected" not in summary:
            return _import_record(row)
    return None


def existing_rows(
    organization_id: str,
    requirements: Sequence[ImportedDailyCoverageRequirement],
) -> dict[tuple[str, str, str, str], dict[str, object]]:
    if not requirements:
        return {}
    dates = sorted({item.operational_date for item in requirements})
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT id, operational_date, station_key, operational_cycle,
                   coverage_segment, source, source_identity
            FROM workforce_daily_coverage_requirements
            WHERE organization_id = ?
              AND operational_date >= ? AND operational_date <= ?
            """,
            (organization_id, dates[0], dates[-1]),
        ).fetchall()
    relevant = {_logical_key(item) for item in requirements}
    result: dict[tuple[str, str, str, str], dict[str, object]] = {}
    for row in rows:
        key = (
            row["operational_date"], row["station_key"],
            row["operational_cycle"], row["coverage_segment"],
        )
        if key not in relevant:
            continue
        candidate = _row_dict(row)
        current = result.get(key)
        if current is None or (
            current["source"] == CoverageSource.LEGACY_IMPORT_BACKFILL.value
            and candidate["source"] != CoverageSource.LEGACY_IMPORT_BACKFILL.value
        ):
            result[key] = candidate
    return result


def _insert_rows(conn, rows: list[tuple[Any, ...]]) -> None:
    conn.executemany(
        """
        INSERT INTO workforce_daily_coverage_requirements (
            organization_id, operational_date, station, station_key,
            operational_cycle, coverage_segment, forecast_routes,
            reserve_percentage, required_capacity, source,
            source_reference, source_identity, authority_status,
            detection_reason, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def apply_missing(
    organization_id: str,
    requirements: Sequence[ImportedDailyCoverageRequirement],
) -> tuple[int, int]:
    now = utc_now_iso()
    with db_session() as conn:
        dates = sorted({item.operational_date for item in requirements})
        rows = conn.execute(
            """
            SELECT operational_date, station_key, operational_cycle,
                   coverage_segment
            FROM workforce_daily_coverage_requirements
            WHERE organization_id = ?
              AND operational_date >= ? AND operational_date <= ?
            """,
            (organization_id, dates[0], dates[-1]),
        ).fetchall()
        existing = {
            (
                row["operational_date"], row["station_key"],
                row["operational_cycle"], row["coverage_segment"],
            )
            for row in rows
        }
        missing = [item for item in requirements if _logical_key(item) not in existing]
        insert_rows = [
            (
                organization_id,
                item.operational_date,
                item.station,
                _station_key(item.station),
                item.operational_cycle,
                _segment_key(item.coverage_segment),
                item.forecast_routes,
                item.reserve_percentage,
                item.required_capacity,
                item.source,
                item.source_reference,
                item.source_identity,
                item.authority_status,
                item.detection_reason,
                now,
                now,
            )
            for item in missing
        ]
        if insert_rows:
            _insert_rows(conn, insert_rows)
    return len(insert_rows), len(requirements) - len(insert_rows)
