from app.domain.assignment_models import (
    Assignment,
    AssignmentSource,
    AssignmentStatus,
)
from app.domain.assignment_rules import station_key
from app.domain.planning_models import PlanningConflict
from app.repositories.assignment_repository import (
    get_assignments,
    update_assignments,
)
from app.repositories.planning_repository import (
    get_planning_record,
    save_version,
    update_planning_record,
)
from app.schemas.planning_schema import (
    GeneratePlanningRequest,
    RecalculatePlanningRequest,
)
from app.services.planning_generation_service import (
    PlanningNotFoundError,
    generate_planning,
    get_planning_bundle,
    refresh_planning_metrics,
    source_resources_for_planning,
)
from app.services.resource_service import build_vehicle_resources
from app.utils.date_utils import utc_now_iso


def _protected(
    assignment: Assignment,
    valid_plates: set[str],
    preserve_manual: bool,
) -> bool:
    if not assignment.confirmed:
        return False
    if not assignment.driver_id or not assignment.plate or assignment.plate not in valid_plates:
        return False
    return not assignment.manual_override or preserve_manual


def recalculate_planning(
    planning_id: int,
    request: RecalculatePlanningRequest,
):
    record = get_planning_record(planning_id)
    if not record:
        raise PlanningNotFoundError(f"Planning {planning_id} non trovato.")
    planning = record["planning"]
    if request.configuration:
        planning.configuration = request.configuration
        planning.reserve_threshold = (
            request.configuration.reserve_vehicle_threshold_global
        )

    current = get_assignments(planning_id)
    planning_rows, fleet_rows = source_resources_for_planning(planning)
    vehicles = build_vehicle_resources(fleet_rows, planning.configuration)
    valid_plates = {
        item.plate for item in vehicles if item.state in {"operational", "reserve"}
    }
    proposal = generate_planning(
        GeneratePlanningRequest(
            planning_import_id=planning.source_planning_import_id,
            fleet_import_id=planning.source_fleet_import_id,
            operation_date=planning.operation_date,
            station=planning.station,
            configuration=planning.configuration,
        ),
        persist=False,
    )
    proposal_by_route = {item.route_id: item for item in proposal.assignments}
    used_drivers: set[str] = set()
    used_plates: set[str] = set()
    recalculated: list[Assignment] = []

    for assignment in current:
        if _protected(
            assignment,
            valid_plates,
            planning.configuration.preserve_confirmed_manual_override,
        ) or "ROUTE_ABORTED" in assignment.warnings:
            recalculated.append(assignment)
            if assignment.driver_id:
                used_drivers.add(assignment.driver_id)
            if assignment.plate:
                used_plates.add(assignment.plate)

    protected_ids = {item.id for item in recalculated}
    for current_assignment in current:
        if current_assignment.id in protected_ids:
            continue
        candidate = proposal_by_route.get(current_assignment.route_id)
        if not candidate:
            recalculated.append(current_assignment)
            continue
        candidate.id = current_assignment.id
        candidate.planning_id = planning_id
        candidate.created_at = current_assignment.created_at
        candidate.updated_at = utc_now_iso()
        candidate.assignment_source = AssignmentSource.RECALCULATED
        candidate.confirmed = False
        candidate.manual_override = False
        candidate.reasons.append("Ricalcolata senza sovrascrivere assegnazioni protette.")

        if candidate.driver_id in used_drivers:
            candidate.driver_id = None
            candidate.driver_name = None
            candidate.warnings.append("DRIVER_ALREADY_ASSIGNED")
        if candidate.plate in used_plates:
            alternative = next(
                (
                    item
                    for item in candidate.alternatives
                    if item.plate and item.plate not in used_plates
                ),
                None,
            )
            if alternative:
                candidate.vehicle_id = alternative.vehicle_id
                candidate.plate = alternative.plate
            else:
                candidate.vehicle_id = None
                candidate.plate = None
                candidate.warnings.append("VEHICLE_ALREADY_ASSIGNED")

        if candidate.driver_id:
            used_drivers.add(candidate.driver_id)
        if candidate.plate:
            used_plates.add(candidate.plate)
        if not candidate.driver_id or not candidate.plate:
            candidate.assignment_status = AssignmentStatus.UNASSIGNED
        elif candidate.warnings:
            candidate.assignment_status = AssignmentStatus.WARNING
        else:
            candidate.assignment_status = AssignmentStatus.PROPOSED
        recalculated.append(candidate)

    recalculated.sort(key=lambda item: (station_key(item.station), item.route_id))
    update_assignments(recalculated)
    planning.version += 1
    conflicts = [
        item
        for item in proposal.conflicts
        if item.code not in {"BLOCKED_ASSIGNMENT", "UNASSIGNED_DRIVER", "UNASSIGNED_VEHICLE"}
    ]
    for assignment in recalculated:
        if not assignment.driver_id:
            conflicts.append(
                PlanningConflict(
                    code="UNASSIGNED_DRIVER",
                    severity="critical",
                    message="Rotta senza driver dopo il ricalcolo.",
                    entity_ref=assignment.route_id,
                )
            )
        if not assignment.plate and "ROUTE_ABORTED" not in assignment.warnings:
            conflicts.append(
                PlanningConflict(
                    code="UNASSIGNED_VEHICLE",
                    severity="critical",
                    message="Rotta senza mezzo dopo il ricalcolo.",
                    entity_ref=assignment.route_id,
                )
            )
    summary, _ = refresh_planning_metrics(planning, recalculated, conflicts)
    update_planning_record(
        planning,
        summary,
        conflicts,
        record["generation_metadata"],
    )
    save_version(
        planning.id,
        planning.version,
        "recalculated",
        {
            "protected_assignments": len(protected_ids),
            "recalculated_assignments": len(recalculated) - len(protected_ids),
            "summary": summary.model_dump(mode="json"),
        },
        request.actor,
    )
    return get_planning_bundle(planning_id)
