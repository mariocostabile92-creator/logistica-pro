import json
from collections.abc import Sequence
from typing import Any

from app.plugins.workforce.domain.coverage import (
    CoverageSource,
    DailyCoverageRequirement,
)


def _segment_key(value: str | None) -> str:
    return str(value or "").strip().upper()


def _identity(
    organization_id: str,
    operational_date: str,
    cycle: str,
    segment: str | None,
) -> str:
    return (
        f"manual-planning:{organization_id}:{operational_date}:"
        f"{cycle}:{_segment_key(segment)}"
    )


def _audit_value(requirement: DailyCoverageRequirement | None) -> dict[str, Any] | None:
    if requirement is None:
        return None
    return {
        "operational_date": requirement.operational_date,
        "cycle": requirement.operational_cycle,
        "segment": requirement.coverage_segment,
        "forecast_routes": requirement.forecast_routes,
        "reserve_percentage": requirement.reserve_percentage,
        "required_capacity": requirement.required_capacity,
        "source": requirement.source,
    }


def save_manual_requirements(
    conn,
    *,
    organization_id: str,
    operational_date: str,
    requirements: Sequence[dict[str, Any]],
    current: dict[tuple[str, str | None], DailyCoverageRequirement],
    actor: str,
    now: str,
) -> int:
    changed = 0
    for item in requirements:
        cycle = str(item["cycle"])
        segment = item.get("segment")
        segment_key = _segment_key(segment)
        source_identity = _identity(
            organization_id, operational_date, cycle, segment
        )
        existing = conn.execute(
            """
            SELECT * FROM workforce_daily_coverage_requirements
            WHERE organization_id = ? AND operational_date = ?
              AND station_key = '' AND operational_cycle = ?
              AND coverage_segment = ? AND source_identity = ?
            """,
            (
                organization_id,
                operational_date,
                cycle,
                segment_key,
                source_identity,
            ),
        ).fetchone()
        values = (
            int(item["forecast_routes"]),
            int(item["reserve_percentage"]),
            int(item["required_capacity"]),
        )
        if existing is not None and (
            int(existing["forecast_routes"]),
            int(existing["reserve_percentage"]),
            int(existing["required_capacity"]),
        ) == values:
            continue

        prior = current.get((cycle, segment))
        if existing is None:
            cursor = conn.execute(
                """
                INSERT INTO workforce_daily_coverage_requirements (
                    organization_id, operational_date, station, station_key,
                    operational_cycle, coverage_segment, forecast_routes,
                    reserve_percentage, required_capacity, source,
                    source_reference, source_identity, created_at, updated_at
                ) VALUES (?, ?, NULL, '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    organization_id,
                    operational_date,
                    cycle,
                    segment_key,
                    *values,
                    CoverageSource.MANUAL_PLANNING_INPUT.value,
                    "planning-day-first",
                    source_identity,
                    now,
                    now,
                ),
            )
            entity_id = str(cursor.lastrowid)
        else:
            entity_id = str(existing["id"])
            conn.execute(
                """
                UPDATE workforce_daily_coverage_requirements
                SET forecast_routes = ?, reserve_percentage = ?,
                    required_capacity = ?, source = ?,
                    source_reference = ?, updated_at = ?
                WHERE id = ? AND organization_id = ?
                """,
                (
                    *values,
                    CoverageSource.MANUAL_PLANNING_INPUT.value,
                    "planning-day-first",
                    now,
                    int(existing["id"]),
                    organization_id,
                ),
            )

        after = {
            "operational_date": operational_date,
            "cycle": cycle,
            "segment": segment,
            "forecast_routes": values[0],
            "reserve_percentage": values[1],
            "required_capacity": values[2],
            "source": CoverageSource.MANUAL_PLANNING_INPUT.value,
        }
        reason = (
            "planning_forecast_manual_set"
            if prior is None
            else "planning_forecast_manual_updated"
        )
        conn.execute(
            """
            INSERT INTO workforce_changes (
                entity_type, entity_id, actor, timestamp, before_value,
                after_value, reason, source, organization_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "daily_coverage_requirement",
                entity_id,
                actor,
                now,
                (
                    json.dumps(_audit_value(prior), ensure_ascii=False, sort_keys=True)
                    if prior is not None
                    else None
                ),
                json.dumps(after, ensure_ascii=False, sort_keys=True),
                reason,
                CoverageSource.MANUAL_PLANNING_INPUT.value,
                organization_id,
            ),
        )
        changed += 1
    return changed
