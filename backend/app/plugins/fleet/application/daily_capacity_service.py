from datetime import date
from collections.abc import Mapping, Sequence

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
VEHICLE_NEED_RULE = "EFFECTIVE_DAILY_OPERATIONAL_REQUIREMENT"
REQUIRED_COVERAGE_BUCKETS = (
    ("NEXT_DAY", None, "NEXT_DAY"),
    ("SAME_DAY", "A", "SAME_DAY_A"),
    ("SAME_DAY", "B_C", "SAME_DAY_B_C"),
)


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


def _value(item: object, key: str):
    if isinstance(item, Mapping):
        return item.get(key)
    return getattr(item, key, None)


def _vehicle_need(
    coverage_items: Sequence[object] | None,
) -> tuple[int | None, str, list[str], list[str]]:
    effective: dict[str, int] = {}
    bucket_names = {
        (cycle, segment): name
        for cycle, segment, name in REQUIRED_COVERAGE_BUCKETS
    }
    for item in coverage_items or ():
        cycle = str(_value(item, "cycle") or "").strip().upper()
        segment_value = _value(item, "segment")
        segment = str(segment_value).strip().upper() if segment_value else None
        name = bucket_names.get((cycle, segment))
        if not name:
            continue
        authority = str(_value(item, "authority_status") or "").strip().upper()
        status = str(_value(item, "status") or "").strip().upper()
        forecast = _value(item, "forecast")
        requirement = _value(item, "requirement")
        if (
            authority == "REJECTED_TEMPLATE"
            or status == "NO_FORECAST"
            or forecast is None
            or requirement is None
        ):
            continue
        effective[name] = effective.get(name, 0) + int(requirement)

    expected = [name for _, _, name in REQUIRED_COVERAGE_BUCKETS]
    known = [name for name in expected if name in effective]
    missing = [name for name in expected if name not in effective]
    if not known:
        return None, "NOT_CONFIGURED", known, missing
    return (
        sum(effective.values()),
        "PARTIAL" if missing else "COMPLETE",
        known,
        missing,
    )


def daily_fleet_capacity(
    *,
    organization_id: str,
    operational_date: str,
    requested_station: str | None = None,
    coverage_items: Sequence[object] | None = None,
    route_assignments_available: bool = False,
    assigned_vehicles: int | None = None,
    routes_without_vehicle: int | None = None,
) -> DailyFleetCapacitySnapshot:
    """Return current Fleet capacity for a requested operational day.

    Fleet does not retain date-scoped availability or an asset station today.
    The requested date/station are therefore context only; the returned counts
    are the current organization-wide canonical operational state.

    Vehicle need is the preliminary daily capacity confirmed by the DSP
    process: the sum of effective Coverage requirements. It remains separate
    from route-level plate assignments.
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
    vehicle_need, need_status, effective_buckets, missing_buckets = (
        _vehicle_need(coverage_items)
    )
    margin = (
        counts["available"] - vehicle_need
        if vehicle_need is not None
        else None
    )
    if vehicle_need is None:
        capacity_status = "NEED_NOT_DETERMINABLE"
        capacity_message = "Fabbisogno mezzi da configurare."
    elif need_status == "PARTIAL":
        capacity_status = "SHORTAGE" if margin < 0 else "SUFFICIENT"
        capacity_message = f"Almeno {vehicle_need} mezzi necessari."
    elif margin < 0:
        capacity_status = "SHORTAGE"
        capacity_message = f"Mancano {abs(margin)} mezzi."
    else:
        capacity_status = "SUFFICIENT"
        capacity_message = "CapacitÃ  Fleet sufficiente."
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
        vehicle_need=vehicle_need,
        vehicle_need_rule=VEHICLE_NEED_RULE,
        vehicle_need_status=need_status,
        effective_requirement_buckets=effective_buckets,
        missing_requirement_buckets=missing_buckets,
        margin=margin,
        capacity_status=capacity_status,
        capacity_message=capacity_message,
        route_assignments_available=route_assignments_available,
        assigned_vehicles=(assigned_vehicles if route_assignments_available else None),
        routes_without_vehicle=(
            routes_without_vehicle if route_assignments_available else None
        ),
        observed_at=observed_at,
    )
