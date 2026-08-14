from app.plugins.dsp_workspace.application.workforce_read_bridge import (
    build_workforce_bridge,
    coverage_projection,
    has_coverage_data,
)
from app.plugins.dsp_workspace.infrastructure.repository import (
    workforce_daily_projection,
)
from app.plugins.workforce.application.coverage_service import daily_coverage


def planning_workforce_input(
    *,
    operation_date: str,
    organization_id: str,
) -> dict[str, object]:
    """Build Planning's date-scoped people and Coverage input.

    The DSP bridge owns the definition of a planned/available/absent driver;
    Coverage owns forecast, requirement and bucket assignment arithmetic.
    Planning only presents those authoritative projections.
    """
    records = workforce_daily_projection(operation_date, organization_id)
    workforce = build_workforce_bridge(records)
    coverage_response = daily_coverage(
        organization_id,
        operation_date,
        operation_date,
    )
    coverage_items, coverage_warnings = coverage_projection(coverage_response)

    planned_ids = {
        row.driver.workforce_member_id
        for row in workforce.rows
        if row.driver.workforce_member_id is not None
    }
    cycle_counts = {"NEXT_DAY": 0, "SAME_DAY": 0, "NOT_SET": 0}
    for record in records:
        if int(record["workforce_member_id"]) not in planned_ids:
            continue
        cycle = str(record.get("operational_cycle") or "NOT_SET").strip().upper()
        cycle_counts[cycle if cycle in cycle_counts else "NOT_SET"] += 1

    forecast_items = [item for item in coverage_items if item.forecast is not None]
    coverage_available = bool(forecast_items)
    requirement_covered = (
        all((item.requirement_gap or 0) == 0 for item in forecast_items)
        if forecast_items
        else None
    )
    drivers = [
        {
            "workforce_member_id": row.driver.workforce_member_id,
            "external_identifier": row.driver.planning_identifier,
            "display_name": row.driver.name,
            "callable": True,
            "selectable": True,
        }
        for row in workforce.rows
    ]
    return {
        "operation_date": operation_date,
        "source": "DSP_WORKFORCE_READ_BRIDGE",
        "summary": {
            "total": len(records),
            "planned": workforce.counts.driver_planned_count,
            "available": workforce.counts.driver_available_count,
            "absent": workforce.counts.driver_absent_count,
            "reserves": workforce.counts.reserve_count,
            "next_day": cycle_counts["NEXT_DAY"],
            "same_day": cycle_counts["SAME_DAY"],
            "not_set": cycle_counts["NOT_SET"],
            # Backwards-compatible aliases used by existing Planning UI helpers.
            "callable": workforce.counts.driver_planned_count,
        },
        "drivers": drivers,
        "coverage": {
            "available": coverage_available,
            "has_data": has_coverage_data(coverage_items),
            "fingerprint": coverage_response.fingerprint,
            "items": [item.model_dump(mode="json") for item in coverage_items],
            "summary": coverage_response.summary.model_dump(mode="json"),
            "requirement_covered": requirement_covered,
        },
        "warnings": [
            warning.model_dump(mode="json")
            for warning in [*workforce.warnings, *coverage_warnings]
        ],
    }
