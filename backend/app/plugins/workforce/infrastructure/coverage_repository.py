from collections.abc import Sequence
from typing import Any

from app.core.database import db_session
from app.plugins.workforce.domain.operational_status import (
    NON_OPERATIONAL_STATUS_CODES,
)
from app.plugins.workforce.domain.coverage import (
    CoverageSource,
    DailyCoverageRequirement,
    ForecastAuthorityStatus,
    ImportedDailyCoverageRequirement,
)


def _station_key(value: str | None) -> str:
    return str(value or "").strip().casefold()


def _segment_key(value: str | None) -> str:
    return str(value or "").strip().upper()


def _requirement_priority(row) -> tuple[int, int]:
    source = row["source"]
    if source == CoverageSource.MANUAL_PLANNING_INPUT.value:
        return 4, 3
    if source == CoverageSource.MANUAL.value:
        return 3, 3
    authority = row["authority_status"]
    authority_priority = {
        ForecastAuthorityStatus.AUTHORITATIVE.value: 3,
        ForecastAuthorityStatus.SUSPECT_TEMPLATE.value: 2,
        ForecastAuthorityStatus.REJECTED_TEMPLATE.value: 1,
    }.get(authority, 0)
    return 2, authority_priority


def persist_imported_requirements(
    conn,
    requirements: Sequence[ImportedDailyCoverageRequirement],
    *,
    organization_id: str,
    now: str,
) -> tuple[int, int]:
    if not requirements:
        return 0, 0
    source_identities = sorted({item.source_identity for item in requirements})
    placeholders = ", ".join("?" for _ in source_identities)
    existing_rows = conn.execute(
        f"""
        SELECT * FROM workforce_daily_coverage_requirements
        WHERE organization_id = ?
          AND source_identity IN ({placeholders})
        """,
        (organization_id, *source_identities),
    ).fetchall()
    existing = {
        (
            row["operational_date"], row["station_key"],
            row["operational_cycle"], row["coverage_segment"],
            row["source_identity"],
        ): row
        for row in existing_rows
    }
    inserts: list[tuple[Any, ...]] = []
    updates: list[tuple[Any, ...]] = []
    for item in requirements:
        station_key = _station_key(item.station)
        segment_key = _segment_key(item.coverage_segment)
        key = (
            item.operational_date, station_key, item.operational_cycle,
            segment_key, item.source_identity,
        )
        row = existing.get(key)
        values = (
            item.forecast_routes,
            item.reserve_percentage,
            item.required_capacity,
            item.source,
            item.source_reference,
            item.authority_status,
            item.detection_reason,
        )
        if row is None:
            inserts.append((
                organization_id,
                item.operational_date,
                item.station,
                station_key,
                item.operational_cycle,
                segment_key,
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
            ))
            continue
        previous = (
            int(row["forecast_routes"]),
            int(row["reserve_percentage"]),
            int(row["required_capacity"]),
            row["source"],
            row["source_reference"],
            row["authority_status"],
            row["detection_reason"],
        )
        if previous != values:
            updates.append((*values, now, int(row["id"]), organization_id))
    if inserts:
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
            inserts,
        )
    if updates:
        conn.executemany(
            """
            UPDATE workforce_daily_coverage_requirements
            SET forecast_routes = ?, reserve_percentage = ?,
                required_capacity = ?, source = ?, source_reference = ?,
                authority_status = ?, detection_reason = ?,
                updated_at = ?
            WHERE id = ? AND organization_id = ?
            """,
            updates,
        )
    return len(inserts), len(updates)


def list_current_requirements_in_connection(
    conn,
    organization_id: str,
    date_from: str,
    date_to: str,
    cycle: str | None = None,
) -> list[DailyCoverageRequirement]:
    conditions = [
        "organization_id = ?",
        "operational_date >= ?",
        "operational_date <= ?",
    ]
    parameters: list[object] = [organization_id, date_from, date_to]
    if cycle:
        conditions.append("operational_cycle = ?")
        parameters.append(cycle)
    rows = conn.execute(
        f"""
        SELECT * FROM workforce_daily_coverage_requirements
        WHERE {' AND '.join(conditions)}
        ORDER BY operational_date, operational_cycle, coverage_segment,
                 station_key, updated_at DESC, id DESC
        """,
        parameters,
    ).fetchall()
    current: dict[tuple[str, str, str, str], Any] = {}
    for row in rows:
        key = (
            row["operational_date"], row["station_key"],
            row["operational_cycle"], row["coverage_segment"],
        )
        selected = current.get(key)
        if selected is None or _requirement_priority(row) > _requirement_priority(
            selected
        ):
            current[key] = row
    return [
        DailyCoverageRequirement(
            coverage_requirement_id=int(row["id"]),
            organization_id=row["organization_id"],
            operational_date=row["operational_date"],
            station=row["station"],
            operational_cycle=row["operational_cycle"],
            coverage_segment=row["coverage_segment"] or None,
            forecast_routes=int(row["forecast_routes"]),
            reserve_percentage=int(row["reserve_percentage"]),
            required_capacity=int(row["required_capacity"]),
            source=row["source"],
            source_reference=row["source_reference"],
            source_identity=row["source_identity"],
            authority_status=row["authority_status"],
            detection_reason=row["detection_reason"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in current.values()
    ]


def list_current_requirements(
    organization_id: str,
    date_from: str,
    date_to: str,
    cycle: str | None = None,
) -> list[DailyCoverageRequirement]:
    with db_session() as conn:
        return list_current_requirements_in_connection(
            conn, organization_id, date_from, date_to, cycle
        )


def assigned_driver_groups(
    organization_id: str,
    date_from: str,
    date_to: str,
) -> list[dict[str, object]]:
    excluded_statuses = sorted(NON_OPERATIONAL_STATUS_CODES)
    status_placeholders = ",".join("?" for _ in excluded_statuses)
    with db_session() as conn:
        rows = conn.execute(
            f"""
            SELECT ds.date, m.operational_cycle, m.station,
                   UPPER(TRIM(ds.shift_code)) AS shift_code,
                   COUNT(*) AS assigned
            FROM workforce_day_statuses ds
            JOIN workforce_members m
              ON m.id = ds.workforce_member_id
             AND m.organization_id = ds.organization_id
            WHERE ds.organization_id = ?
              AND ds.date >= ? AND ds.date <= ?
                AND ds.availability = 1
                AND ds.shift_code IS NOT NULL
                AND LOWER(TRIM(COALESCE(ds.status_code, 'unknown')))
                    NOT IN ({status_placeholders})
            GROUP BY ds.date, m.operational_cycle, m.station,
                     UPPER(TRIM(ds.shift_code))
              """,
              (organization_id, date_from, date_to, *excluded_statuses),
        ).fetchall()
    return [
        {
            "date": row["date"],
            "operational_cycle": row["operational_cycle"],
            "station": row["station"],
            "shift_code": row["shift_code"],
            "assigned": int(row["assigned"]),
        }
        for row in rows
    ]
