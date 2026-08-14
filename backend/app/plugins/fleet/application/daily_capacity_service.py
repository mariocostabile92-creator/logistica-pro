from datetime import date

from app.plugins.fleet.domain.daily_capacity import (
    DailyFleetCapacitySnapshot,
)
from app.plugins.fleet.infrastructure import repository


AVAILABLE = frozenset({
    "available",
    "reserve",
    "disponibile",
    "disponibile_con_limitazioni",
})
UNAVAILABLE = frozenset({"unavailable", "indisponibile", "fermo"})
MAINTENANCE = frozenset({"maintenance", "in_manutenzione"})
BLOCKED = frozenset({"workshop", "in_officina"})


def classify_availability(value: str | None) -> str:
    normalized = str(value or "").strip().casefold()
    if normalized in AVAILABLE:
        return "available"
    if normalized in UNAVAILABLE:
        return "unavailable"
    if normalized in MAINTENANCE:
        return "maintenance"
    if normalized in BLOCKED:
        return "blocked"
    return "unknown"


def daily_fleet_capacity(
    *,
    organization_id: str,
    operational_date: str,
    requested_station: str | None = None,
    route_assignments_available: bool = False,
    assigned_vehicles: int | None = None,
    routes_without_vehicle: int | None = None,
) -> DailyFleetCapacitySnapshot:
    """Return current Fleet capacity for a requested operational day.

    Fleet does not retain date-scoped availability or an asset station today.
    The requested date/station are therefore context only; the returned counts
    are the current organization-wide canonical operational state.

    No route/driver forecast is converted into a vehicle need because no
    authoritative cross-cycle reuse rule exists yet.
    """
    operation_day = date.fromisoformat(operational_date).isoformat()
    organization = str(organization_id or "").strip()
    if not organization:
        raise ValueError("organization_id is required")

    rows, observed_at = repository.availability_counts(organization)
    counts = {
        "available": 0,
        "unavailable": 0,
        "maintenance": 0,
        "blocked": 0,
        "unknown": 0,
    }
    for row in rows:
        category = classify_availability(str(row.get("availability") or ""))
        counts[category] += int(row.get("count") or 0)

    total = sum(counts.values())
    return DailyFleetCapacitySnapshot(
        operational_date=operation_day,
        requested_station=(str(requested_station).strip() or None)
        if requested_station is not None
        else None,
        station_scope_applied=False,
        total_vehicles=total,
        available_vehicles=counts["available"],
        unavailable_vehicles=counts["unavailable"],
        maintenance_vehicles=counts["maintenance"],
        blocked_vehicles=counts["blocked"],
        unknown_vehicles=counts["unknown"],
        vehicle_need=None,
        vehicle_need_rule=None,
        margin=None,
        capacity_status="NEED_NOT_DETERMINABLE",
        capacity_message="Fabbisogno mezzi non ancora determinabile.",
        route_assignments_available=route_assignments_available,
        assigned_vehicles=(assigned_vehicles if route_assignments_available else None),
        routes_without_vehicle=(
            routes_without_vehicle if route_assignments_available else None
        ),
        observed_at=observed_at,
    )

