from datetime import date, datetime, timezone

from app.plugins.dsp_workspace.domain.models import (
    DailyOperationsSnapshot,
    PlanningMetadata,
    SourceMetadata,
)
from app.plugins.dsp_workspace.application.row_builder import build_operational_rows
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

    return DailyOperationsSnapshot(
        operation_date=day,
        generated_at=_now(),
        planning=planning,
        sources=sources,
        rows=built.rows,
        signals=built.signals,
        partial=any(item.partial for item in sources.values()),
    )
