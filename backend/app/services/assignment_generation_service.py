from collections import Counter

from app.domain.assignment_models import (
    Assignment,
    AssignmentAlternative,
    AssignmentSource,
    AssignmentStatus,
)
from app.domain.assignment_rules import station_key
from app.domain.normalized_models import NormalizedFleetRow, NormalizedPlanningRow
from app.domain.planning_models import (
    DriverResource,
    PlanningConfiguration,
    VehicleResource,
)
from app.services.resource_service import (
    build_driver_resources,
    build_vehicle_resources,
)
from app.utils.date_utils import utc_now_iso


def _resolve_station(
    row: NormalizedPlanningRow,
    drivers_by_id: dict[str, DriverResource],
    vehicles_by_plate: dict[str, VehicleResource],
    station_filter: str | None,
) -> str:
    if row.station:
        return row.station
    if row.vehicle_plate and row.vehicle_plate in vehicles_by_plate:
        return vehicles_by_plate[row.vehicle_plate].station
    if row.driver_key and row.driver_key in drivers_by_id:
        return drivers_by_id[row.driver_key].station
    return station_filter or "UNSPECIFIED"


def _eligible_vehicles(
    vehicles: list[VehicleResource],
    station: str,
    used_plates: set[str],
) -> list[VehicleResource]:
    same_station = [
        vehicle
        for vehicle in vehicles
        if station_key(vehicle.station) == station_key(station)
        and vehicle.plate not in used_plates
        and vehicle.state in {"operational", "reserve"}
    ]
    return sorted(
        same_station,
        key=lambda item: (item.state == "reserve", item.plate),
    )


def _alternatives(
    candidates: list[VehicleResource],
    selected_plate: str | None,
    maximum: int,
) -> list[AssignmentAlternative]:
    alternatives: list[AssignmentAlternative] = []
    for candidate in candidates:
        if candidate.plate == selected_plate:
            continue
        alternatives.append(
            AssignmentAlternative(
                vehicle_id=candidate.id,
                plate=candidate.plate,
                confidence=0.72 if candidate.state == "operational" else 0.58,
                reason=f"Mezzo {candidate.state} disponibile nella stessa station.",
                not_selected_reason=(
                    "Priorità inferiore rispetto al mezzo selezionato."
                    if selected_plate
                    else "Nessuna selezione automatica applicata."
                ),
            )
        )
        if len(alternatives) >= maximum:
            break
    return alternatives


def generate_assignments(
    planning_rows: list[NormalizedPlanningRow],
    fleet_rows: list[NormalizedFleetRow],
    operation_date: str,
    configuration: PlanningConfiguration,
    station_filter: str | None = None,
) -> tuple[
    list[Assignment],
    list[DriverResource],
    list[VehicleResource],
]:
    now = utc_now_iso()
    drivers = build_driver_resources(planning_rows, fleet_rows)
    vehicles = build_vehicle_resources(fleet_rows, configuration)
    drivers_by_id = {item.id: item for item in drivers}
    vehicles_by_plate = {item.plate: item for item in vehicles}
    used_drivers: set[str] = set()
    used_plates: set[str] = set()
    assignments: list[Assignment] = []
    driver_route_counts = Counter(
        row.driver_key for row in planning_rows if row.driver_key
    )

    for row in planning_rows:
        station = _resolve_station(
            row,
            drivers_by_id,
            vehicles_by_plate,
            station_filter,
        )
        driver_id = row.driver_key
        driver_name = row.driver_name
        warnings: list[str] = []
        reasons: list[str] = []
        data_used = [f"planning_row:{row.row_number}"]
        selected_vehicle: VehicleResource | None = None
        source = AssignmentSource.FALLBACK
        confidence = 0.0
        status = AssignmentStatus.UNASSIGNED

        if not driver_id:
            warnings.append("DRIVER_MISSING")
            reasons.append("La rotta non contiene un driver riconosciuto.")
        elif driver_id in used_drivers:
            warnings.append("DRIVER_ALREADY_ASSIGNED")
            reasons.append("Il driver è già utilizzato su un'altra rotta.")
            driver_id = None
            driver_name = None
        else:
            used_drivers.add(driver_id)
            if driver_route_counts[row.driver_key] > 1:
                warnings.append("DUPLICATE_DRIVER_SOURCE")

        candidates = _eligible_vehicles(vehicles, station, used_plates)

        if row.vehicle_plate and configuration.preserve_imported_assignment:
            imported = vehicles_by_plate.get(row.vehicle_plate)
            if (
                imported
                and imported.state in {"operational", "reserve"}
                and imported.plate not in used_plates
                and station_key(imported.station) == station_key(station)
            ):
                selected_vehicle = imported
                source = AssignmentSource.IMPORTED_ASSIGNMENT
                confidence = 0.99
                reasons.append("Assegnazione mezzo conservata dal planning importato.")
                data_used.append(f"imported_plate:{row.vehicle_plate}")
            else:
                source = AssignmentSource.IMPORTED_ASSIGNMENT
                status = AssignmentStatus.BLOCKED
                warnings.append("IMPORTED_VEHICLE_INVALID")
                reasons.append(
                    "Il mezzo importato non è disponibile, valido o compatibile con la station."
                )
                assignment = Assignment(
                    operation_date=operation_date,
                    station=station,
                    route_id=row.route or "",
                    cycle_or_wave=row.cycle,
                    driver_id=driver_id,
                    driver_name=driver_name,
                    vehicle_id=row.vehicle_plate,
                    plate=row.vehicle_plate,
                    assignment_status=status,
                    assignment_source=source,
                    confidence=0.25,
                    reasons=reasons,
                    data_used=data_used,
                    warnings=warnings,
                    alternatives=_alternatives(
                        candidates,
                        None,
                        configuration.maximum_alternatives_per_assignment,
                    ),
                    created_at=now,
                    updated_at=now,
                )
                assignments.append(assignment)
                continue

        if (
            not selected_vehicle
            and driver_id
            and configuration.prefer_habitual_vehicle
            and driver_id in drivers_by_id
        ):
            habitual_plate = drivers_by_id[driver_id].habitual_plate
            habitual = vehicles_by_plate.get(habitual_plate or "")
            if (
                habitual
                and habitual.state in {"operational", "reserve"}
                and habitual.plate not in used_plates
                and station_key(habitual.station) == station_key(station)
            ):
                selected_vehicle = habitual
                source = AssignmentSource.HABITUAL_VEHICLE
                confidence = 0.9
                reasons.append(
                    f"Mezzo abituale derivato dal parco auto per {driver_name}."
                )
                data_used.append(f"fleet_habitual_plate:{habitual.plate}")
            elif habitual_plate:
                warnings.append("HABITUAL_VEHICLE_UNAVAILABLE")

        if not selected_vehicle and driver_id and candidates:
            selected_vehicle = candidates[0]
            source = (
                AssignmentSource.RESERVE_VEHICLE
                if selected_vehicle.state == "reserve"
                else AssignmentSource.AVAILABLE_VEHICLE
            )
            confidence = 0.72 if selected_vehicle.state == "operational" else 0.58
            reasons.append(
                "Primo mezzo libero compatibile della stessa station, ordinato per priorità."
            )
            data_used.append(f"fleet_available_plate:{selected_vehicle.plate}")
            if selected_vehicle.state == "reserve":
                warnings.append("RESERVE_VEHICLE_USED")

        if selected_vehicle:
            used_plates.add(selected_vehicle.plate)
            status = AssignmentStatus.WARNING if warnings else AssignmentStatus.PROPOSED
        elif driver_id:
            warnings.append("VEHICLE_MISSING")
            reasons.append("Nessun mezzo operativo libero nella stessa station.")

        assignments.append(
            Assignment(
                operation_date=operation_date,
                station=station,
                route_id=row.route or "",
                cycle_or_wave=row.cycle,
                driver_id=driver_id,
                driver_name=driver_name,
                vehicle_id=selected_vehicle.id if selected_vehicle else None,
                plate=selected_vehicle.plate if selected_vehicle else None,
                assignment_status=status,
                assignment_source=source,
                confidence=confidence,
                reasons=reasons,
                data_used=data_used,
                warnings=warnings,
                alternatives=_alternatives(
                    candidates,
                    selected_vehicle.plate if selected_vehicle else None,
                    configuration.maximum_alternatives_per_assignment,
                ),
                created_at=now,
                updated_at=now,
            )
        )

    return assignments, drivers, vehicles
