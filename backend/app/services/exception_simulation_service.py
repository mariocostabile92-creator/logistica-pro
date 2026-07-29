from app.domain.assignment_models import (
    Assignment,
    AssignmentSource,
    AssignmentStatus,
)
from app.domain.assignment_rules import station_key
from app.domain.operation_events import (
    EventSimulation,
    OperationEntityType,
    OperationEvent,
    OperationEventType,
)
from app.domain.planning_diff import AssignmentChange, PlanningDiff
from app.domain.planning_models import (
    DriverResource,
    PlanningConflict,
    VehicleResource,
)
from app.repositories.assignment_repository import (
    insert_assignment,
    update_assignment,
)
from app.repositories.event_repository import list_events, save_event
from app.repositories.planning_repository import (
    get_planning_record,
    save_version,
    update_planning_record,
)
from app.schemas.planning_event_schema import PlanningEventRequest
from app.services.event_resource_service import apply_resource_event_constraints
from app.services.resource_service import (
    build_driver_resources,
    build_vehicle_resources,
)
from app.services.planning_generation_service import (
    PlanningNotFoundError,
    get_planning_bundle,
    refresh_planning_metrics,
    source_resources_for_planning,
)
from app.services.station_capacity_service import calculate_station_capacity
from app.utils.date_utils import utc_now_iso
from app.utils.text_normalizer import compact_key, normalize_plate


class EventSimulationError(ValueError):
    pass


def effective_resources_for_planning(planning):
    planning_rows, fleet_rows = source_resources_for_planning(planning)
    drivers = build_driver_resources(planning_rows, fleet_rows)
    vehicles = build_vehicle_resources(fleet_rows, planning.configuration)
    events = list_events(planning.id) if planning.id else []
    return apply_resource_event_constraints(drivers, vehicles, events)


def _assignment_change(before: Assignment | None, after: Assignment) -> AssignmentChange:
    fields = (
        "driver_id",
        "driver_name",
        "vehicle_id",
        "plate",
        "assignment_status",
        "assignment_source",
        "warnings",
    )
    changed_fields = [
        field
        for field in fields
        if before is None or getattr(before, field) != getattr(after, field)
    ]
    return AssignmentChange(
        assignment_id=before.id if before else None,
        route_id=after.route_id,
        change_type="event_simulation",
        before=before.model_dump(mode="json") if before else None,
        after=after.model_dump(mode="json"),
        changed_fields=changed_fields,
    )


def _driver_candidate(
    station: str,
    drivers: list[DriverResource],
    used_driver_ids: set[str],
    excluded_driver_id: str,
) -> DriverResource | None:
    return next(
        (
            driver
            for driver in drivers
            if station_key(driver.station) == station_key(station)
            and driver.id not in used_driver_ids
            and driver.id != excluded_driver_id
        ),
        None,
    )


def _vehicle_candidate(
    station: str,
    vehicles: list[VehicleResource],
    used_plates: set[str],
    excluded_plate: str,
) -> VehicleResource | None:
    candidates = [
        vehicle
        for vehicle in vehicles
        if station_key(vehicle.station) == station_key(station)
        and vehicle.state in {"operational", "reserve"}
        and vehicle.plate not in used_plates
        and vehicle.plate != excluded_plate
    ]
    candidates.sort(key=lambda item: (item.state == "reserve", item.plate))
    return candidates[0] if candidates else None


def simulate_event(
    planning_id: int,
    request: PlanningEventRequest,
) -> EventSimulation:
    bundle = get_planning_bundle(planning_id)
    planning = bundle.planning
    drivers, vehicles = effective_resources_for_planning(planning)
    before_drivers = [item.model_copy(deep=True) for item in drivers]
    before_vehicles = [item.model_copy(deep=True) for item in vehicles]
    before_assignments = [item.model_copy(deep=True) for item in bundle.assignments]
    proposed = [item.model_copy(deep=True) for item in bundle.assignments]
    used_driver_ids = {item.driver_id for item in proposed if item.driver_id}
    used_plates = {item.plate for item in proposed if item.plate}
    changes: list[AssignmentChange] = []
    now = utc_now_iso()

    if request.event_type == OperationEventType.DRIVER_ABSENT:
        driver_id = compact_key(request.entity_id)
        impacted = [
            item
            for item in proposed
            if item.driver_id == driver_id
            or compact_key(item.driver_name) == driver_id
        ]
        if not impacted:
            raise EventSimulationError("Driver non assegnato nel planning.")
        for assignment in impacted:
            before = assignment.model_copy(deep=True)
            used_driver_ids.discard(assignment.driver_id)
            replacement = _driver_candidate(
                assignment.station,
                drivers,
                used_driver_ids,
                driver_id,
            )
            if replacement:
                assignment.driver_id = replacement.id
                assignment.driver_name = replacement.name
                assignment.assignment_status = AssignmentStatus.WARNING
                assignment.warnings.append("DRIVER_ABSENT_REPLACED")
                assignment.reasons.append(
                    f"Driver libero {replacement.name} proposto per assenza."
                )
                used_driver_ids.add(replacement.id)
            else:
                assignment.driver_id = None
                assignment.driver_name = None
                assignment.assignment_status = AssignmentStatus.UNASSIGNED
                assignment.warnings.append("DRIVER_ABSENT_NO_REPLACEMENT")
                assignment.reasons.append("Nessun driver libero compatibile.")
            assignment.assignment_source = AssignmentSource.RECALCULATED
            assignment.confirmed = False
            assignment.updated_at = now
            changes.append(_assignment_change(before, assignment))

    elif request.event_type == OperationEventType.VEHICLE_UNAVAILABLE:
        plate = normalize_plate(request.entity_id)
        impacted = [item for item in proposed if item.plate == plate]
        if not impacted:
            raise EventSimulationError("Mezzo non assegnato nel planning.")
        for assignment in impacted:
            before = assignment.model_copy(deep=True)
            used_plates.discard(assignment.plate)
            replacement = _vehicle_candidate(
                assignment.station,
                vehicles,
                used_plates,
                plate,
            )
            if replacement:
                assignment.vehicle_id = replacement.id
                assignment.plate = replacement.plate
                assignment.assignment_status = AssignmentStatus.WARNING
                assignment.warnings.append("VEHICLE_KO_REPLACED")
                assignment.reasons.append(
                    f"Mezzo {replacement.plate} proposto per indisponibilità."
                )
                used_plates.add(replacement.plate)
            else:
                assignment.vehicle_id = None
                assignment.plate = None
                assignment.assignment_status = AssignmentStatus.UNASSIGNED
                assignment.warnings.append("VEHICLE_KO_NO_REPLACEMENT")
                assignment.reasons.append("Nessun mezzo libero compatibile.")
            assignment.assignment_source = AssignmentSource.RECALCULATED
            assignment.confirmed = False
            assignment.updated_at = now
            changes.append(_assignment_change(before, assignment))
        for vehicle in vehicles:
            if vehicle.plate == plate:
                vehicle.state = "blocked"

    elif request.event_type == OperationEventType.ROUTE_ABORTED:
        impacted = [item for item in proposed if item.route_id == request.entity_id]
        if not impacted:
            raise EventSimulationError("Rotta non presente nel planning.")
        for assignment in impacted:
            before = assignment.model_copy(deep=True)
            assignment.driver_id = None
            assignment.driver_name = None
            assignment.vehicle_id = None
            assignment.plate = None
            assignment.assignment_status = AssignmentStatus.INVALIDATED
            assignment.assignment_source = AssignmentSource.RECALCULATED
            assignment.confirmed = False
            assignment.warnings.append("ROUTE_ABORTED")
            assignment.reasons.append("Rotta rimossa dalla necessità operativa.")
            assignment.updated_at = now
            changes.append(_assignment_change(before, assignment))

    elif request.event_type == OperationEventType.ROUTE_ADDED:
        route_id = str(request.payload.get("route_id") or request.entity_id)
        station = str(request.payload.get("station") or planning.station or "")
        if not route_id or not station:
            raise EventSimulationError("route_id e station sono obbligatori.")
        if any(item.route_id == route_id for item in proposed):
            raise EventSimulationError("Rotta già presente nel planning.")
        assignment = Assignment(
            planning_id=planning.id,
            operation_date=planning.operation_date,
            station=station,
            route_id=route_id,
            cycle_or_wave=str(request.payload.get("cycle_or_wave") or "") or None,
            assignment_status=AssignmentStatus.UNASSIGNED,
            assignment_source=AssignmentSource.RECALCULATED,
            reasons=["Rotta aggiunta tramite evento operativo."],
            warnings=["DRIVER_MISSING", "VEHICLE_MISSING"],
            created_at=now,
            updated_at=now,
        )
        proposed.append(assignment)
        changes.append(_assignment_change(None, assignment))

    elif request.event_type in {
        OperationEventType.DRIVER_RESTORED,
        OperationEventType.VEHICLE_RESTORED,
    }:
        impacted = [
            item
            for item in proposed
            if item.route_id == str(request.payload.get("route_id") or "")
        ]
        if not impacted:
            raise EventSimulationError(
                "Per un ripristino indicare payload.route_id della rotta da ricalcolare."
            )
        for assignment in impacted:
            before = assignment.model_copy(deep=True)
            if request.event_type == OperationEventType.DRIVER_RESTORED:
                assignment.driver_id = compact_key(request.entity_id)
                assignment.driver_name = request.entity_id
                assignment.warnings = [
                    item for item in assignment.warnings if "DRIVER_ABSENT" not in item
                ]
            else:
                plate = normalize_plate(request.entity_id)
                assignment.vehicle_id = plate
                assignment.plate = plate
                assignment.warnings = [
                    item for item in assignment.warnings if "VEHICLE_KO" not in item
                ]
            assignment.assignment_status = AssignmentStatus.WARNING
            assignment.updated_at = now
            changes.append(_assignment_change(before, assignment))
    else:
        raise EventSimulationError("Tipo evento non simulabile da questo endpoint.")

    if not changes:
        raise EventSimulationError("L'evento non produce modifiche.")

    before_capacity = calculate_station_capacity(
        before_assignments,
        before_drivers,
        before_vehicles,
        planning.configuration,
    )
    if request.event_type == OperationEventType.DRIVER_ABSENT:
        absent_id = compact_key(request.entity_id)
        drivers = [item for item in drivers if item.id != absent_id]
    after_capacity = calculate_station_capacity(
        proposed,
        drivers,
        vehicles,
        planning.configuration,
    )
    diff = PlanningDiff(
        planning_id=planning_id,
        event_type=request.event_type.value,
        summary=f"{len(changes)} assegnazioni coinvolte da {request.event_type.value}.",
        assignment_changes=changes,
        station_capacity_before=before_capacity,
        station_capacity_after=after_capacity,
        warnings=[
            issue
            for capacity in after_capacity
            for issue in capacity.issues
        ],
    )
    event = OperationEvent(
        planning_id=planning_id,
        event_type=request.event_type,
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        reason=request.reason,
        simulated=True,
        applied=False,
        impact_summary=diff.summary,
        payload=request.payload,
        actor=request.actor,
        created_at=now,
    )
    return EventSimulation(
        event=event,
        diff=diff,
        proposed_assignments=proposed,
    )


def apply_event(
    planning_id: int,
    request: PlanningEventRequest,
):
    simulation = simulate_event(planning_id, request)
    record = get_planning_record(planning_id)
    if not record:
        raise PlanningNotFoundError(f"Planning {planning_id} non trovato.")
    planning = record["planning"]
    existing_ids = {
        item.id for item in get_planning_bundle(planning_id).assignments
    }
    for assignment in simulation.proposed_assignments:
        if assignment.id in existing_ids:
            update_assignment(assignment)
        else:
            insert_assignment(assignment)

    now = utc_now_iso()
    simulation.event.applied = True
    simulation.event.applied_at = now
    save_event(simulation.event, simulation.diff)
    planning.version += 1
    conflicts = [
        item
        for item in record["conflicts"]
        if item.code not in {"UNASSIGNED_DRIVER", "UNASSIGNED_VEHICLE"}
    ]
    for assignment in simulation.proposed_assignments:
        if "ROUTE_ABORTED" in assignment.warnings:
            continue
        if not assignment.driver_id:
            conflicts.append(
                PlanningConflict(
                    code="UNASSIGNED_DRIVER",
                    severity="critical",
                    message="Rotta scoperta dopo evento operativo.",
                    entity_ref=assignment.route_id,
                )
            )
        if not assignment.plate:
            conflicts.append(
                PlanningConflict(
                    code="UNASSIGNED_VEHICLE",
                    severity="critical",
                    message="Rotta senza mezzo dopo evento operativo.",
                    entity_ref=assignment.route_id,
                )
            )
    summary, _ = refresh_planning_metrics(
        planning,
        simulation.proposed_assignments,
        conflicts,
    )
    update_planning_record(
        planning,
        summary,
        conflicts,
        record["generation_metadata"],
    )
    save_version(
        planning.id,
        planning.version,
        f"event:{request.event_type.value}",
        simulation.diff.model_dump(mode="json"),
        request.actor,
    )
    return get_planning_bundle(planning_id), simulation.event, simulation.diff
