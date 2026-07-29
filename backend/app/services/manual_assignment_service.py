from app.domain.assignment_models import Assignment, AssignmentSource, AssignmentStatus
from app.domain.assignment_rules import station_key
from app.domain.operation_events import (
    OperationEntityType,
    OperationEvent,
    OperationEventType,
)
from app.domain.planning_diff import AssignmentChange, PlanningDiff
from app.domain.planning_models import PlanningConflict
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
from app.schemas.assignment_schema import PatchAssignmentRequest
from app.services.planning_generation_service import (
    get_planning_bundle,
    refresh_planning_metrics,
    source_resources_for_planning,
)
from app.services.resource_service import (
    build_driver_resources,
    build_vehicle_resources,
)
from app.utils.date_utils import utc_now_iso
from app.utils.text_normalizer import compact_key, normalize_plate


class AssignmentValidationError(ValueError):
    pass


def patch_assignment(
    assignment_id: int,
    request: PatchAssignmentRequest,
) -> Assignment:
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
            raise AssignmentValidationError(
                "Driver non presente nei dataset normalizzati."
            )
        if (
            station_key(driver.station) != station_key(assignment.station)
            and not request.allow_cross_station
        ):
            raise AssignmentValidationError(
                "Driver appartenente a una station incompatibile."
            )
        if any(
            item.id != assignment.id
            and item.driver_id == driver.id
            and "ROUTE_ABORTED" not in item.warnings
            for item in all_assignments
        ):
            raise AssignmentValidationError(
                "Driver già assegnato a un'altra rotta."
            )
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
            raise AssignmentValidationError(
                "Mezzo non disponibile per l'assegnazione."
            )
        if (
            station_key(vehicle.station) != station_key(assignment.station)
            and not request.allow_cross_station
        ):
            raise AssignmentValidationError(
                "Mezzo appartenente a una station incompatibile."
            )
        if any(
            item.id != assignment.id
            and item.plate == vehicle.plate
            and "ROUTE_ABORTED" not in item.warnings
            for item in all_assignments
        ):
            raise AssignmentValidationError(
                "Mezzo già assegnato a un'altra rotta."
            )
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
