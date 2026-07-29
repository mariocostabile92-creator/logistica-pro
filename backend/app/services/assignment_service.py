from collections import Counter

from app.domain.assignment_models import (
    Assignment,
    AssignmentAlternative,
    AssignmentSource,
    AssignmentStatus,
)
from app.domain.assignment_rules import station_key, vehicle_operational_state
from app.domain.normalized_models import NormalizedFleetRow, NormalizedPlanningRow
from app.domain.planning_models import (
    DriverResource,
    PlanningConfiguration,
    PlanningConflict,
    VehicleResource,
)
from app.schemas.assignment_schema import PatchAssignmentRequest
from app.utils.date_utils import utc_now_iso
from app.utils.text_normalizer import compact_key, normalize_plate


def build_driver_resources(
    planning_rows: list[NormalizedPlanningRow],
    fleet_rows: list[NormalizedFleetRow],
) -> list[DriverResource]:
    resources: dict[str, DriverResource] = {}
    for row in fleet_rows:
        if row.driver_key and row.driver_name:
            resources.setdefault(
                row.driver_key,
                DriverResource(
                    id=row.driver_key,
                    name=row.driver_name,
                    station=row.station or "UNSPECIFIED",
                    habitual_plate=row.vehicle_plate,
                ),
            )
        if row.second_driver_key and row.second_driver_name:
            resources.setdefault(
                row.second_driver_key,
                DriverResource(
                    id=row.second_driver_key,
                    name=row.second_driver_name,
                    station=row.station or "UNSPECIFIED",
                ),
            )
    for row in planning_rows:
        if row.driver_key and row.driver_name:
            resources.setdefault(
                row.driver_key,
                DriverResource(
                    id=row.driver_key,
                    name=row.driver_name,
                    station=row.station or "UNSPECIFIED",
                ),
            )
    return sorted(resources.values(), key=lambda item: (item.station, item.name))


def build_vehicle_resources(
    fleet_rows: list[NormalizedFleetRow],
    configuration: PlanningConfiguration,
) -> list[VehicleResource]:
    resources: dict[str, VehicleResource] = {}
    for row in fleet_rows:
        if not row.vehicle_plate or row.vehicle_plate in resources:
            continue
        resources[row.vehicle_plate] = VehicleResource(
            id=row.vehicle_plate,
            plate=row.vehicle_plate,
            station=row.station or "UNSPECIFIED",
            state=vehicle_operational_state(
                row,
                configuration.blocked_vehicle_statuses,
                configuration.unrecognized_status_is_blocking,
            ),
            habitual_driver_id=row.driver_key,
        )
    return sorted(resources.values(), key=lambda item: (item.station, item.plate))


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
    driver_route_counts = Counter(row.driver_key for row in planning_rows if row.driver_key)

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


class AssignmentValidationError(ValueError):
    pass


def patch_assignment(
    assignment_id: int,
    request: PatchAssignmentRequest,
):
    from app.domain.operation_events import (
        OperationEntityType,
        OperationEvent,
        OperationEventType,
    )
    from app.domain.planning_diff import AssignmentChange, PlanningDiff
    from app.repositories.assignment_repository import (
        get_assignment,
        get_assignments,
        update_assignment,
    )
    from app.repositories.event_repository import save_event
    from app.repositories.planning_repository import (
        get_planning_record,
        save_version,
        update_planning_record,
    )
    from app.services.planning_generation_service import (
        get_planning_bundle,
        refresh_planning_metrics,
        source_resources_for_planning,
    )

    assignment = get_assignment(assignment_id)
    if not assignment:
        raise AssignmentValidationError("Assegnazione non trovata.")
    record = get_planning_record(assignment.planning_id)
    if not record:
        raise AssignmentValidationError("Planning dell'assegnazione non trovato.")
    planning = record["planning"]
    before_bundle = get_planning_bundle(planning.id)
    before = assignment.model_copy(deep=True)
    all_assignments = get_assignments(planning.id)
    planning_rows, fleet_rows = source_resources_for_planning(planning)
    drivers = build_driver_resources(planning_rows, fleet_rows)
    vehicles = build_vehicle_resources(fleet_rows, planning.configuration)
    drivers_by_id = {item.id: item for item in drivers}
    vehicles_by_plate = {item.plate: item for item in vehicles}

    driver_changed = False
    vehicle_changed = False
    if request.remove_driver:
        assignment.driver_id = None
        assignment.driver_name = None
        driver_changed = True
    elif request.driver_id is not None or request.driver_name is not None:
        driver_id = request.driver_id or compact_key(request.driver_name)
        driver = drivers_by_id.get(driver_id)
        if not driver:
            raise AssignmentValidationError("Driver non presente nei dataset normalizzati.")
        if (
            station_key(driver.station) != station_key(assignment.station)
            and not request.allow_cross_station
        ):
            raise AssignmentValidationError("Driver appartenente a una station incompatibile.")
        if any(
            item.id != assignment.id
            and item.driver_id == driver.id
            and "ROUTE_ABORTED" not in item.warnings
            for item in all_assignments
        ):
            raise AssignmentValidationError("Driver già assegnato a un'altra rotta.")
        assignment.driver_id = driver.id
        assignment.driver_name = request.driver_name or driver.name
        driver_changed = (
            before.driver_id != assignment.driver_id
            or before.driver_name != assignment.driver_name
        )

    if request.remove_vehicle:
        assignment.vehicle_id = None
        assignment.plate = None
        vehicle_changed = True
    elif request.vehicle_id is not None or request.plate is not None:
        plate = normalize_plate(request.plate or request.vehicle_id)
        vehicle = vehicles_by_plate.get(plate)
        if not vehicle:
            raise AssignmentValidationError("Mezzo non presente nel parco auto.")
        if vehicle.state not in {"operational", "reserve"}:
            raise AssignmentValidationError("Mezzo non disponibile per l'assegnazione.")
        if (
            station_key(vehicle.station) != station_key(assignment.station)
            and not request.allow_cross_station
        ):
            raise AssignmentValidationError("Mezzo appartenente a una station incompatibile.")
        if any(
            item.id != assignment.id
            and item.plate == vehicle.plate
            and "ROUTE_ABORTED" not in item.warnings
            for item in all_assignments
        ):
            raise AssignmentValidationError("Mezzo già assegnato a un'altra rotta.")
        assignment.vehicle_id = vehicle.id
        assignment.plate = vehicle.plate
        vehicle_changed = (
            before.vehicle_id != assignment.vehicle_id
            or before.plate != assignment.plate
        )

    if request.confirm is True and (not assignment.driver_id or not assignment.plate):
        raise AssignmentValidationError(
            "Non è possibile confermare un'assegnazione senza driver e mezzo."
        )

    changed = driver_changed or vehicle_changed or request.note is not None
    if changed:
        assignment.assignment_source = AssignmentSource.MANUAL
        assignment.manual_override = request.manual_override
        assignment.confidence = 1.0
        assignment.reasons.append("Modifica manuale confermata dall'operatore.")
        assignment.data_used.append(f"actor:{request.actor}")
    if request.note is not None:
        assignment.notes = request.note
    if request.confirm is not None:
        assignment.confirmed = request.confirm

    assignment.warnings = [
        item
        for item in assignment.warnings
        if item
        not in {
            "DRIVER_MISSING",
            "DRIVER_ALREADY_ASSIGNED",
            "VEHICLE_MISSING",
            "IMPORTED_VEHICLE_INVALID",
        }
    ]
    if not assignment.driver_id:
        assignment.warnings.append("DRIVER_MISSING")
    if not assignment.plate:
        assignment.warnings.append("VEHICLE_MISSING")
    if assignment.confirmed:
        assignment.assignment_status = AssignmentStatus.CONFIRMED
    elif changed:
        assignment.assignment_status = AssignmentStatus.MANUALLY_CHANGED
    elif assignment.warnings:
        assignment.assignment_status = AssignmentStatus.WARNING
    else:
        assignment.assignment_status = AssignmentStatus.PROPOSED
    assignment.updated_at = utc_now_iso()
    update_assignment(assignment)

    planning.version += 1
    conflicts = [
        item
        for item in record["conflicts"]
        if not (
            item.entity_ref == assignment.route_id
            and item.code
            in {
                "BLOCKED_ASSIGNMENT",
                "UNASSIGNED_DRIVER",
                "UNASSIGNED_VEHICLE",
            }
        )
    ]
    if not assignment.driver_id:
        conflicts.append(
            PlanningConflict(
                code="UNASSIGNED_DRIVER",
                severity="critical",
                message="Rotta senza driver assegnato.",
                entity_ref=assignment.route_id,
            )
        )
    if not assignment.plate:
        conflicts.append(
            PlanningConflict(
                code="UNASSIGNED_VEHICLE",
                severity="critical",
                message="Rotta senza mezzo assegnato.",
                entity_ref=assignment.route_id,
            )
        )
    current_assignments = get_assignments(planning.id)
    summary, capacity = refresh_planning_metrics(
        planning,
        current_assignments,
        conflicts,
    )
    update_planning_record(
        planning,
        summary,
        conflicts,
        record["generation_metadata"],
    )
    changed_fields = [
        field
        for field in (
            "driver_id",
            "driver_name",
            "vehicle_id",
            "plate",
            "confirmed",
            "notes",
        )
        if getattr(before, field) != getattr(assignment, field)
    ]
    change = AssignmentChange(
        assignment_id=assignment.id,
        route_id=assignment.route_id,
        change_type="manual_assignment_change",
        before=before.model_dump(mode="json"),
        after=assignment.model_dump(mode="json"),
        changed_fields=changed_fields,
    )
    change_type = (
        "manual_assignment_change"
        if driver_changed or vehicle_changed or request.note is not None
        else "assignment_confirmation"
    )
    diff = PlanningDiff(
        planning_id=planning.id,
        event_type=change_type,
        summary=(
            f"Assegnazione {assignment.route_id} modificata manualmente."
            if change_type == "manual_assignment_change"
            else f"Assegnazione {assignment.route_id} confermata."
        ),
        assignment_changes=[change],
        station_capacity_before=before_bundle.station_capacity,
        station_capacity_after=capacity,
    )
    save_version(
        planning.id,
        planning.version,
        change_type,
        diff.model_dump(mode="json"),
        request.actor,
    )
    if driver_changed or vehicle_changed:
        event = OperationEvent(
            planning_id=planning.id,
            event_type=(
                OperationEventType.VEHICLE_CHANGED
                if vehicle_changed
                else OperationEventType.DRIVER_CHANGED
            ),
            entity_type=OperationEntityType.ASSIGNMENT,
            entity_id=str(assignment.id),
            reason=request.note or "Modifica manuale assegnazione.",
            simulated=False,
            applied=True,
            impact_summary=diff.summary,
            actor=request.actor,
            created_at=assignment.updated_at,
            applied_at=assignment.updated_at,
        )
        save_event(event, diff)
    return assignment


# Compatibility exports for callers that still import the historical module.
# Production modules depend on the focused services directly.
from app.services.assignment_generation_service import (  # noqa: E402
    generate_assignments as _generate_assignments,
)
from app.services.manual_assignment_service import (  # noqa: E402
    AssignmentValidationError as _AssignmentValidationError,
    patch_assignment as _patch_assignment,
)
from app.services.resource_service import (  # noqa: E402
    build_driver_resources as _build_driver_resources,
    build_vehicle_resources as _build_vehicle_resources,
)

build_driver_resources = _build_driver_resources
build_vehicle_resources = _build_vehicle_resources
generate_assignments = _generate_assignments
AssignmentValidationError = _AssignmentValidationError
patch_assignment = _patch_assignment
