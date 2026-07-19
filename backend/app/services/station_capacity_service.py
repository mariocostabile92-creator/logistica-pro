from collections import defaultdict

from app.domain.assignment_models import Assignment
from app.domain.assignment_rules import station_key
from app.domain.planning_models import (
    CrossStationSuggestion,
    DriverResource,
    PlanningConfiguration,
    StationCapacity,
    StationRisk,
    VehicleResource,
)


def calculate_station_capacity(
    assignments: list[Assignment],
    drivers: list[DriverResource],
    vehicles: list[VehicleResource],
    configuration: PlanningConfiguration,
) -> list[StationCapacity]:
    assignments_by_station: dict[str, list[Assignment]] = defaultdict(list)
    drivers_by_station: dict[str, set[str]] = defaultdict(set)
    vehicles_by_station: dict[str, list[VehicleResource]] = defaultdict(list)

    for assignment in assignments:
        assignments_by_station[station_key(assignment.station)].append(assignment)
    for driver in drivers:
        drivers_by_station[station_key(driver.station)].add(driver.id)
    for vehicle in vehicles:
        vehicles_by_station[station_key(vehicle.station)].append(vehicle)

    station_names = {
        station_key(assignment.station): assignment.station for assignment in assignments
    }
    for driver in drivers:
        station_names.setdefault(station_key(driver.station), driver.station)
    for vehicle in vehicles:
        station_names.setdefault(station_key(vehicle.station), vehicle.station)

    capacities: list[StationCapacity] = []
    for key, display_name in sorted(station_names.items()):
        station_assignments = assignments_by_station.get(key, [])
        active_assignments = [
            item
            for item in station_assignments
            if "ROUTE_ABORTED" not in item.warnings
        ]
        station_vehicles = vehicles_by_station.get(key, [])
        operational = [
            item for item in station_vehicles if item.state in {"operational", "reserve"}
        ]
        assigned_driver_ids = {
            item.driver_id for item in active_assignments if item.driver_id
        }
        assigned_plates = {
            item.plate for item in active_assignments if item.plate
        }
        available_driver_ids = drivers_by_station.get(key, set()) | assigned_driver_ids
        routes_total = len(active_assignments)
        operational_margin = len(operational) - routes_total
        threshold = configuration.reserve_threshold_for(display_name)
        issues: list[str] = []

        if routes_total > len(operational):
            risk = StationRisk.CRITICAL
            issues.append("Rotte superiori ai mezzi operativi.")
        elif routes_total > len(available_driver_ids):
            risk = StationRisk.CRITICAL
            issues.append("Rotte superiori ai driver disponibili.")
        elif operational_margin == 0:
            risk = StationRisk.HIGH
            issues.append("Nessun margine operativo.")
        elif operational_margin < threshold:
            risk = StationRisk.MEDIUM
            issues.append("Margine sotto la soglia di riserva.")
        else:
            risk = StationRisk.LOW

        capacities.append(
            StationCapacity(
                station=display_name,
                routes_total=routes_total,
                drivers_available=len(available_driver_ids),
                drivers_assigned=len(assigned_driver_ids),
                drivers_unused=max(
                    len(available_driver_ids) - len(assigned_driver_ids),
                    0,
                ),
                physical_vehicles=len(station_vehicles),
                operational_vehicles=len(operational),
                assigned_vehicles=len(assigned_plates),
                free_vehicles=max(len(operational) - len(assigned_plates), 0),
                safe_reserve_vehicles=max(len(operational) - routes_total, 0),
                blocked_vehicles=len(station_vehicles) - len(operational),
                deficit_or_surplus=operational_margin,
                operational_margin=operational_margin,
                reserve_threshold=threshold,
                readiness=risk,
                issues=issues,
            )
        )

    if configuration.allow_cross_station_suggestion:
        assigned_plates = {item.plate for item in assignments if item.plate}
        for target in capacities:
            if target.operational_margin >= 0:
                continue
            for donor in capacities:
                if donor.station == target.station:
                    continue
                transferable = donor.operational_margin - donor.reserve_threshold
                if transferable <= 0:
                    continue
                candidate = next(
                    (
                        vehicle
                        for vehicle in vehicles
                        if station_key(vehicle.station) == station_key(donor.station)
                        and vehicle.state in {"operational", "reserve"}
                        and vehicle.plate not in assigned_plates
                    ),
                    None,
                )
                if not candidate:
                    continue
                target.cross_station_suggestions.append(
                    CrossStationSuggestion(
                        from_station=donor.station,
                        to_station=target.station,
                        plate=candidate.plate,
                        source_margin_before=donor.operational_margin,
                        source_margin_after=donor.operational_margin - 1,
                        target_deficit_before=target.operational_margin,
                        reason="Surplus oltre la riserva della station cedente.",
                    )
                )
                break

    return capacities
