from datetime import date, datetime, timezone

from app.plugins.dsp_workspace.domain.models import (
    DailyOperationsSnapshot,
    PlanningMetadata,
    SourceMetadata,
)
from app.plugins.dsp_workspace.application.row_builder import build_operational_rows
from app.plugins.dsp_workspace.application.operational_signals import (
    apply_operational_projections,
)
from app.plugins.dsp_workspace.infrastructure import repository
from app.plugins.workforce.application.availability_service import (
    foundation_snapshot,
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
    try:
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

    fleet_fetched_at = _now()
    fleet_assets: list[dict] = []
    try:
        fleet_assets = repository.compact_fleet_assets(organization_id)
        sources["fleet"] = _source(
            available=True,
            status="available",
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

    if planning_snapshot:
        planning_record = planning_snapshot["planning"]
        planning = PlanningMetadata(
            available=True,
            planning_id=int(planning_record["id"]),
            operation_date=day,
            status=str(planning_record["status"]),
            updated_at=planning_record.get("updated_at"),
        )
    else:
        planning = PlanningMetadata(available=False, operation_date=day)

    built = build_operational_rows(
        organization_id=organization_id,
        planning_snapshot=planning_snapshot,
        workforce_drivers=workforce_drivers,
        fleet_assets=fleet_assets,
    )

    asset_ids = [
        row.vehicle.fleet_asset_id
        for row in built.rows
        if row.vehicle.fleet_asset_id is not None
    ]
    workforce_member_ids = [
        row.driver.workforce_member_id
        for row in built.rows
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
        rows=built.rows,
        journal_records=journal_records,
        damage_cases=damage_cases,
        operation_date=day,
        timezone_name=str(clock["timezone"]),
        operational_day_start_hour=int(clock["operational_day_start_hour"]),
        journal_available=sources["journal"].available,
        damage_available=sources["damage"].available,
        now=now,
    )
    if built.unresolved_drivers and sources["workforce"].available:
        sources["workforce"] = sources["workforce"].model_copy(update={
            "status": "partial_unresolved_identity",
            "partial": True,
        })
    if built.unresolved_vehicles and sources["fleet"].available:
        sources["fleet"] = sources["fleet"].model_copy(update={
            "status": "partial_unresolved_identity",
            "partial": True,
        })
    if operational.journal_partial_rows and sources["journal"].available:
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
        rows=operational.rows,
        signals=[*built.signals, *operational.signals],
        partial=any(item.partial for item in sources.values()),
    )
