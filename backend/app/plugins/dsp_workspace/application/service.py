from datetime import date, datetime, timezone

from app.plugins.dsp_workspace.domain.models import (
    DailyOperationsCounts,
    DailyOperationsSnapshot,
    PlanningMetadata,
    SourceMetadata,
)
from app.plugins.dsp_workspace.application.row_builder import build_operational_rows
from app.plugins.dsp_workspace.application.operational_signals import (
    apply_operational_projections,
)
from app.plugins.dsp_workspace.infrastructure import repository
from app.plugins.dsp_workspace.application.workforce_read_bridge import (
    build_workforce_bridge,
    coverage_projection,
    has_coverage_data,
)
from app.plugins.workforce.application.availability_service import (
    foundation_snapshot,
)
from app.plugins.workforce.application.coverage_service import daily_coverage
from app.plugins.fleet.application.daily_capacity_service import (
    daily_fleet_capacity,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source(
    *,
    available: bool,
    status: str,
    fetched_at: str,
    partial: bool = False,
    error: str | None = None,
) -> SourceMetadata:
    return SourceMetadata(
        available=available,
        status=status,
        fetched_at=fetched_at,
        partial=partial,
        error=error,
    )


def _safe_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: source unavailable"


def daily_operations_snapshot(
    *,
    operation_date: str,
    organization_id: str,
    now: datetime | None = None,
) -> DailyOperationsSnapshot:
    day = date.fromisoformat(operation_date).isoformat()
    organization_id = str(organization_id or "").strip()
    if not organization_id:
        raise ValueError("organization_id is required")

    sources: dict[str, SourceMetadata] = {}
    planning_snapshot: dict | None = None
    planning_fetched_at = _now()
    try:
        planning_snapshot = repository.authoritative_planning_snapshot(
            day,
            organization_id,
        )
        sources["planning"] = _source(
            available=True,
            status=("available" if planning_snapshot else "no_authoritative_planning"),
            fetched_at=planning_fetched_at,
        )
    except Exception as exc:
        sources["planning"] = _source(
            available=False,
            status="unavailable",
            fetched_at=planning_fetched_at,
            partial=True,
            error=_safe_error(exc),
        )

    workforce_fetched_at = _now()
    workforce_drivers: dict[int, object] = {}
    workforce_records: list[dict[str, object]] = []
    workforce_bridge = build_workforce_bridge([])
    try:
        workforce_records = repository.workforce_daily_projection(day, organization_id)
        workforce_bridge = build_workforce_bridge(workforce_records)
        if planning_snapshot:
            workforce = foundation_snapshot(day, organization_id)
            workforce_drivers = {
                driver.workforce_member_id: driver
                for driver in workforce.drivers
            }
        sources["workforce"] = _source(
            available=True,
            status="available",
            fetched_at=workforce_fetched_at,
        )
    except Exception as exc:
        sources["workforce"] = _source(
            available=False,
            status="unavailable",
            fetched_at=workforce_fetched_at,
            partial=True,
            error=_safe_error(exc),
        )

    coverage_fetched_at = _now()
    coverage_items = []
    coverage_warnings = []
    try:
        coverage_response = daily_coverage(organization_id, day, day)
        coverage_items, coverage_warnings = coverage_projection(coverage_response)
        sources["coverage"] = _source(
            available=True,
            status=("available" if has_coverage_data(coverage_items) else "no_data"),
            fetched_at=coverage_fetched_at,
        )
    except Exception as exc:
        sources["coverage"] = _source(
            available=False,
            status="unavailable",
            fetched_at=coverage_fetched_at,
            partial=True,
            error=_safe_error(exc),
        )

    fleet_fetched_at = _now()
    fleet_assets: list[dict] = []
    fleet_capacity = None
    try:
        fleet_capacity = daily_fleet_capacity(
            organization_id=organization_id,
            operational_date=day,
            coverage_items=coverage_items,
            requested_station=(
                str(planning_snapshot["planning"].get("station") or "").strip()
                or None
                if planning_snapshot
                else None
            ),
            route_assignments_available=bool(planning_snapshot),
            assigned_vehicles=(
                sum(
                    bool(item.get("plate"))
                    for item in planning_snapshot.get("assignments", [])
                )
                if planning_snapshot
                else None
            ),
            routes_without_vehicle=(
                sum(
                    not bool(item.get("plate"))
                    for item in planning_snapshot.get("assignments", [])
                )
                if planning_snapshot
                else None
            ),
        )
        if planning_snapshot:
            fleet_assets = repository.compact_fleet_assets(organization_id)
        sources["fleet"] = _source(
            available=True,
            status=(
                "available"
                if fleet_capacity.total_vehicles
                else "no_data"
            ),
            fetched_at=fleet_fetched_at,
        )
    except Exception as exc:
        sources["fleet"] = _source(
            available=False,
            status="unavailable",
            fetched_at=fleet_fetched_at,
            partial=True,
            error=_safe_error(exc),
        )

    workforce_fallback_available = bool(workforce_bridge.rows) or has_coverage_data(
        coverage_items
    )
    if planning_snapshot:
        planning_record = planning_snapshot["planning"]
        planning = PlanningMetadata(
            available=True,
            planning_id=int(planning_record["id"]),
            operation_date=day,
            status=str(planning_record["status"]),
            updated_at=planning_record.get("updated_at"),
        )
        source_type = "LEGACY_OPERATIONAL_PLANNING"
        planning_status = str(planning_record["status"])
    else:
        planning = PlanningMetadata(
            available=workforce_fallback_available,
            operation_date=day,
            status=("available" if workforce_fallback_available else None),
            source="workforce-operational-projection",
        )
        source_type = (
            "WORKFORCE_OPERATIONAL_PROJECTION"
            if workforce_fallback_available else None
        )
        planning_status = (
            "workforce_available" if workforce_fallback_available else "no_data"
        )

    if planning_snapshot:
        built = build_operational_rows(
            organization_id=organization_id,
            planning_snapshot=planning_snapshot,
            workforce_drivers=workforce_drivers,
            fleet_assets=fleet_assets,
        )
        built_rows = built.rows
        built_signals = built.signals
        legacy_member_ids = {
            row.driver.workforce_member_id
            for row in built_rows
            if row.driver.workforce_member_id is not None
        }
        counts = DailyOperationsCounts(
            driver_planned_count=len(built_rows),
            driver_available_count=workforce_bridge.counts.driver_available_count,
            driver_absent_count=workforce_bridge.counts.driver_absent_count,
            reserve_count=sum(
                bool(record.get("is_reserve"))
                and int(record["workforce_member_id"]) in legacy_member_ids
                for record in workforce_records
            ),
        )
        bridge_warnings = []
    else:
        built = None
        built_rows = workforce_bridge.rows
        built_signals = []
        counts = workforce_bridge.counts
        bridge_warnings = workforce_bridge.warnings

    asset_ids = [
        row.vehicle.fleet_asset_id
        for row in built_rows
        if row.vehicle.fleet_asset_id is not None
    ]
    workforce_member_ids = [
        row.driver.workforce_member_id
        for row in built_rows
        if row.driver.workforce_member_id is not None
    ]

    journal_fetched_at = _now()
    journal_records: list[dict] = []
    clock = {"timezone": "Europe/Rome", "operational_day_start_hour": 4}
    try:
        clock = repository.organization_clock(organization_id)
        journal_records = repository.compact_journal_records(
            day,
            organization_id,
            asset_ids,
        )
        sources["journal"] = _source(
            available=True,
            status="available",
            fetched_at=journal_fetched_at,
        )
    except Exception as exc:
        sources["journal"] = _source(
            available=False,
            status="unavailable",
            fetched_at=journal_fetched_at,
            partial=True,
            error=_safe_error(exc),
        )

    damage_fetched_at = _now()
    damage_cases: list[dict] = []
    try:
        damage_cases = repository.compact_open_damage_cases(
            organization_id,
            asset_ids,
            workforce_member_ids,
        )
        sources["damage"] = _source(
            available=True,
            status="available",
            fetched_at=damage_fetched_at,
        )
    except Exception as exc:
        sources["damage"] = _source(
            available=False,
            status="unavailable",
            fetched_at=damage_fetched_at,
            partial=True,
            error=_safe_error(exc),
        )

    operational = apply_operational_projections(
        rows=built_rows,
        journal_records=journal_records,
        damage_cases=damage_cases,
        operation_date=day,
        timezone_name=str(clock["timezone"]),
        operational_day_start_hour=int(clock["operational_day_start_hour"]),
        journal_available=sources["journal"].available,
        damage_available=sources["damage"].available,
        now=now,
    )
    if built and built.unresolved_drivers and sources["workforce"].available:
        sources["workforce"] = sources["workforce"].model_copy(update={
            "status": "partial_unresolved_identity",
            "partial": True,
        })
    if built and built.unresolved_vehicles and sources["fleet"].available:
        sources["fleet"] = sources["fleet"].model_copy(update={
            "status": "partial_unresolved_identity",
            "partial": True,
        })
    if (
        planning_snapshot
        and operational.journal_partial_rows
        and sources["journal"].available
    ):
        sources["journal"] = sources["journal"].model_copy(update={
            "status": "partial_unresolved_correlation",
            "partial": True,
        })
    if operational.damage_partial_rows and sources["damage"].available:
        sources["damage"] = sources["damage"].model_copy(update={
            "status": "partial_unresolved_correlation",
            "partial": True,
        })

    return DailyOperationsSnapshot(
        operation_date=day,
        generated_at=_now(),
        planning=planning,
        sources=sources,
        source_type=source_type,
        planning_status=planning_status,
        counts=counts,
        coverage=coverage_items,
        fleet_capacity=(
            fleet_capacity.model_dump(mode="json")
            if fleet_capacity is not None
            else None
        ),
        warnings=[*bridge_warnings, *coverage_warnings],
        rows=operational.rows,
        signals=[*built_signals, *operational.signals],
        partial=any(item.partial for item in sources.values()),
    )
