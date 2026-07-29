from datetime import date

from app.domain.assignment_models import AssignmentStatus
from app.domain.assignment_rules import station_key
from app.domain.normalized_models import NormalizedFleetRow, NormalizedPlanningRow
from app.domain.planning_models import (
    GenerationMetadata,
    OperationalPlanning,
    PlanningBundle,
    PlanningConfiguration,
    PlanningConflict,
    PlanningStatus,
    PlanningSummary,
    StationRisk,
)
from app.repositories.assignment_repository import get_assignments
from app.repositories.event_repository import list_events
from app.repositories.import_repository import get_import, get_latest_import
from app.repositories.planning_repository import (
    create_planning,
    get_latest_planning_record,
    get_planning_record,
    list_versions,
)
from app.schemas.planning_schema import GeneratePlanningRequest
from app.services.assignment_generation_service import generate_assignments
from app.services.event_resource_service import apply_resource_event_constraints
from app.services.resource_service import (
    build_driver_resources,
    build_vehicle_resources,
)
from app.services.planning_validation_service import PlanningValidationError, validate_generation_inputs
from app.services.station_capacity_service import calculate_station_capacity
from app.utils.date_utils import utc_now_iso


class PlanningNotFoundError(LookupError):
    pass


def _active_assignments(assignments):
    return [
        item for item in assignments if "ROUTE_ABORTED" not in item.warnings
    ]


def _resolve_import(
    import_id: int | None,
    dataset_type: str,
) -> dict[str, object]:
    item = (
        get_import(import_id, dataset_type)
        if import_id is not None
        else get_latest_import(dataset_type)
    )
    if not item:
        label = "planning" if dataset_type == "planning" else "parco auto"
        raise PlanningValidationError(
            f"Nessun import {label} disponibile.",
            code=f"MISSING_{dataset_type.upper()}_IMPORT",
        )
    return item


def _source_rows(
    planning_import: dict[str, object],
    fleet_import: dict[str, object],
    station_filter: str | None,
) -> tuple[list[NormalizedPlanningRow], list[NormalizedFleetRow]]:
    planning_rows = [
        NormalizedPlanningRow.model_validate(item)
        for item in planning_import["normalized_rows"]
    ]
    fleet_rows = [
        NormalizedFleetRow.model_validate(item)
        for item in fleet_import["normalized_rows"]
    ]
    if station_filter:
        requested = station_key(station_filter)
        planning_rows = [
            row for row in planning_rows if station_key(row.station) == requested
        ]
    return planning_rows, fleet_rows


def _summary(
    assignments,
    conflicts: list[PlanningConflict],
    station_capacity,
) -> PlanningSummary:
    active_assignments = _active_assignments(assignments)
    assigned = [
        item
        for item in active_assignments
        if item.driver_id
        and item.plate
        and item.assignment_status
        not in {
            AssignmentStatus.BLOCKED,
            AssignmentStatus.UNASSIGNED,
            AssignmentStatus.INVALIDATED,
        }
    ]
    return PlanningSummary(
        routes_total=len(active_assignments),
        routes_assigned=len(assigned),
        routes_unassigned=len(active_assignments) - len(assigned),
        assignments_confirmed=sum(
            1 for item in active_assignments if item.confirmed
        ),
        manual_overrides=sum(
            1 for item in active_assignments if item.manual_override
        ),
        drivers_used=len({item.driver_id for item in assigned if item.driver_id}),
        vehicles_used=len({item.plate for item in assigned if item.plate}),
        stations=len([item for item in station_capacity if item.routes_total]),
        critical_conflicts=sum(
            1 for item in conflicts if item.severity == "critical"
        ),
        warnings=sum(1 for item in conflicts if item.severity == "warning")
        + sum(1 for item in active_assignments if item.warnings),
    )


def _status(
    assignments,
    conflicts: list[PlanningConflict],
    station_capacity,
) -> PlanningStatus:
    active_assignments = _active_assignments(assignments)
    if any(item.readiness == StationRisk.CRITICAL for item in station_capacity):
        return PlanningStatus.CRITICAL
    if any(item.blocking or item.severity == "critical" for item in conflicts):
        return PlanningStatus.CRITICAL
    if active_assignments and all(item.confirmed for item in active_assignments):
        return PlanningStatus.CONFIRMED
    if any(
        item.assignment_status
        in {
            AssignmentStatus.BLOCKED,
            AssignmentStatus.UNASSIGNED,
            AssignmentStatus.INVALIDATED,
        }
        for item in active_assignments
    ):
        return PlanningStatus.PARTIALLY_ASSIGNED
    return PlanningStatus.READY


def _assignment_conflicts(assignments) -> list[PlanningConflict]:
    conflicts: list[PlanningConflict] = []
    for assignment in _active_assignments(assignments):
        if assignment.assignment_status == AssignmentStatus.BLOCKED:
            conflicts.append(
                PlanningConflict(
                    code="BLOCKED_ASSIGNMENT",
                    severity="critical",
                    message="Assegnazione importata non utilizzabile.",
                    entity_ref=assignment.route_id,
                    suggested_action="Seleziona una delle alternative dopo aver verificato i dati.",
                )
            )
        elif not assignment.driver_id:
            conflicts.append(
                PlanningConflict(
                    code="UNASSIGNED_DRIVER",
                    severity="critical",
                    message="Rotta senza driver assegnato.",
                    entity_ref=assignment.route_id,
                    suggested_action="Scegli un driver libero compatibile.",
                )
            )
        elif not assignment.plate:
            conflicts.append(
                PlanningConflict(
                    code="UNASSIGNED_VEHICLE",
                    severity="critical",
                    message="Rotta senza mezzo assegnato.",
                    entity_ref=assignment.route_id,
                    suggested_action="Scegli un mezzo operativo della stessa station.",
                )
            )
    return conflicts


def _operation_date(
    requested: str | None,
    planning_import: dict[str, object],
) -> tuple[str, str]:
    if requested:
        try:
            return date.fromisoformat(requested).isoformat(), "request"
        except ValueError as exc:
            raise PlanningValidationError(
                "operation_date deve usare il formato YYYY-MM-DD.",
                code="INVALID_OPERATION_DATE",
            ) from exc
    imported_at = str(planning_import["imported_at"])
    return imported_at[:10], "planning_import_timestamp"


def generate_planning(
    request: GeneratePlanningRequest,
    persist: bool = True,
) -> PlanningBundle:
    planning_import = _resolve_import(request.planning_import_id, "planning")
    fleet_import = _resolve_import(request.fleet_import_id, "fleet")
    configuration = request.configuration or PlanningConfiguration()
    planning_rows, fleet_rows = _source_rows(
        planning_import,
        fleet_import,
        request.station,
    )
    conflicts = validate_generation_inputs(
        planning_rows,
        fleet_rows,
        request.station,
        configuration.blocked_vehicle_statuses,
    )
    if str(planning_import["imported_at"])[:10] != str(fleet_import["imported_at"])[:10]:
        conflicts.append(
            PlanningConflict(
                code="IMPORT_DATE_MISMATCH",
                severity="warning",
                message="Planning e parco auto sono stati importati in date diverse.",
                entity_ref="imports",
                suggested_action="Conferma che i due dataset descrivano la stessa giornata operativa.",
            )
        )

    operation_date, operation_date_source = _operation_date(
        request.operation_date,
        planning_import,
    )
    assignments, drivers, vehicles = generate_assignments(
        planning_rows,
        fleet_rows,
        operation_date,
        configuration,
        request.station,
    )
    conflicts.extend(_assignment_conflicts(assignments))
    station_capacity = calculate_station_capacity(
        assignments,
        drivers,
        vehicles,
        configuration,
    )
    now = utc_now_iso()
    planning = OperationalPlanning(
        operation_date=operation_date,
        station=request.station,
        source_planning_import_id=int(planning_import["id"]),
        source_fleet_import_id=int(fleet_import["id"]),
        status=PlanningStatus.GENERATED,
        version=1,
        reserve_threshold=configuration.reserve_vehicle_threshold_global,
        configuration=configuration,
        created_at=now,
        updated_at=now,
    )
    summary = _summary(assignments, conflicts, station_capacity)
    planning.status = _status(assignments, conflicts, station_capacity)
    used_driver_ids = {item.driver_id for item in assignments if item.driver_id}
    used_plates = {item.plate for item in assignments if item.plate}
    available_vehicles = [
        item
        for item in vehicles
        if item.state in {"operational", "reserve"} and item.plate not in used_plates
    ]
    metadata = GenerationMetadata(
        generated_at=now,
        planning_import_id=int(planning_import["id"]),
        fleet_import_id=int(fleet_import["id"]),
        operation_date_source=operation_date_source,
        applied_rules=[
            "validate_inputs",
            "exclude_unavailable_vehicles",
            "preserve_imported_assignment",
            "prefer_habitual_vehicle",
            "assign_same_station_vehicle",
            "preserve_reserve_when_possible",
            "suggest_cross_station_without_applying",
        ],
    )
    bundle = PlanningBundle(
        planning=planning,
        summary=summary,
        assignments=assignments,
        unassigned_routes=[
            item.route_id
            for item in _active_assignments(assignments)
            if not item.driver_id
            or not item.plate
            or item.assignment_status == AssignmentStatus.BLOCKED
        ],
        unused_drivers=[item for item in drivers if item.id not in used_driver_ids],
        available_vehicles=available_vehicles,
        reserve_vehicles=[
            item for item in available_vehicles if item.state == "reserve"
        ],
        station_capacity=station_capacity,
        conflicts=conflicts,
        generation_metadata=metadata,
    )
    return create_planning(bundle) if persist else bundle


def source_resources_for_planning(
    planning: OperationalPlanning,
) -> tuple[list[NormalizedPlanningRow], list[NormalizedFleetRow]]:
    planning_import = _resolve_import(
        planning.source_planning_import_id,
        "planning",
    )
    fleet_import = _resolve_import(
        planning.source_fleet_import_id,
        "fleet",
    )
    return _source_rows(planning_import, fleet_import, planning.station)


def bundle_from_record(record: dict[str, object]) -> PlanningBundle:
    planning = record["planning"]
    assignments = get_assignments(planning.id)
    planning_rows, fleet_rows = source_resources_for_planning(planning)
    drivers = build_driver_resources(planning_rows, fleet_rows)
    vehicles = build_vehicle_resources(fleet_rows, planning.configuration)
    events = list_events(planning.id)
    if events:
        drivers, vehicles = apply_resource_event_constraints(
            drivers,
            vehicles,
            events,
        )
    station_capacity = calculate_station_capacity(
        assignments,
        drivers,
        vehicles,
        planning.configuration,
    )
    used_driver_ids = {item.driver_id for item in assignments if item.driver_id}
    used_plates = {item.plate for item in assignments if item.plate}
    available_vehicles = [
        item
        for item in vehicles
        if item.state in {"operational", "reserve"} and item.plate not in used_plates
    ]
    return PlanningBundle(
        planning=planning,
        summary=record["summary"],
        assignments=assignments,
        unassigned_routes=[
            item.route_id
            for item in _active_assignments(assignments)
            if not item.driver_id
            or not item.plate
            or item.assignment_status
            in {
                AssignmentStatus.BLOCKED,
                AssignmentStatus.UNASSIGNED,
                AssignmentStatus.INVALIDATED,
            }
        ],
        unused_drivers=[item for item in drivers if item.id not in used_driver_ids],
        available_vehicles=available_vehicles,
        reserve_vehicles=[
            item for item in available_vehicles if item.state == "reserve"
        ],
        station_capacity=station_capacity,
        conflicts=record["conflicts"],
        generation_metadata=record["generation_metadata"],
        history={
            "versions": list_versions(planning.id),
            "events": events,
        },
    )


def get_planning_bundle(planning_id: int) -> PlanningBundle:
    record = get_planning_record(planning_id)
    if not record:
        raise PlanningNotFoundError(f"Planning {planning_id} non trovato.")
    return bundle_from_record(record)


def get_latest_planning_bundle() -> PlanningBundle:
    record = get_latest_planning_record()
    if not record:
        raise PlanningNotFoundError("Nessun planning generato.")
    return bundle_from_record(record)


def refresh_planning_metrics(
    planning: OperationalPlanning,
    assignments,
    conflicts: list[PlanningConflict],
):
    planning_rows, fleet_rows = source_resources_for_planning(planning)
    drivers = build_driver_resources(planning_rows, fleet_rows)
    vehicles = build_vehicle_resources(fleet_rows, planning.configuration)
    if planning.id:
        events = list_events(planning.id)
        if events:
            drivers, vehicles = apply_resource_event_constraints(
                drivers,
                vehicles,
                events,
            )
    capacity = calculate_station_capacity(
        assignments,
        drivers,
        vehicles,
        planning.configuration,
    )
    summary = _summary(assignments, conflicts, capacity)
    planning.status = _status(assignments, conflicts, capacity)
    planning.updated_at = utc_now_iso()
    return summary, capacity
