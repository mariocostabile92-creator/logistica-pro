import csv
import io

import pytest

from app.domain.assignment_models import AssignmentSource, AssignmentStatus
from app.domain.operation_events import (
    OperationEntityType,
    OperationEventType,
)
from app.schemas.assignment_schema import PatchAssignmentRequest
from app.schemas.planning_event_schema import PlanningEventRequest
from app.schemas.planning_schema import (
    GeneratePlanningRequest,
    RecalculatePlanningRequest,
)
from app.services.assignment_service import (
    AssignmentValidationError,
    patch_assignment,
)
from app.services.exception_simulation_service import (
    apply_event,
    simulate_event,
)
from app.services.planning_export_service import export_planning_csv
from app.services.planning_generation_service import (
    generate_planning,
    get_planning_bundle,
)
from app.services.planning_recalculation_service import recalculate_planning
from tests.planning_helpers import save_normalized_imports, simple_rows


def generated_bundle(routes: int = 1, drivers: int = 2, vehicles: int = 2):
    planning, fleet = simple_rows(routes, drivers, vehicles)
    planning_id, fleet_id = save_normalized_imports(planning, fleet)
    return generate_planning(
        GeneratePlanningRequest(
            planning_import_id=planning_id,
            fleet_import_id=fleet_id,
            operation_date="2026-07-20",
        )
    )


def event_request(
    event_type: OperationEventType,
    entity_type: OperationEntityType,
    entity_id: str,
) -> PlanningEventRequest:
    return PlanningEventRequest(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        reason="Test operativo sintetico",
    )


def test_manual_vehicle_change():
    bundle = generated_bundle()
    assignment = patch_assignment(
        bundle.assignments[0].id,
        PatchAssignmentRequest(plate="AA002AA", confirm=True),
    )
    assert assignment.plate == "AA002AA"
    assert assignment.manual_override is True
    assert assignment.assignment_source == AssignmentSource.MANUAL


def test_manual_driver_change():
    bundle = generated_bundle()
    assignment = patch_assignment(
        bundle.assignments[0].id,
        PatchAssignmentRequest(
            driver_id="driver02",
            driver_name="Driver 02",
            confirm=True,
        ),
    )
    assert assignment.driver_id == "driver02"
    assert assignment.assignment_status == AssignmentStatus.CONFIRMED


def test_manual_override_is_preserved_during_recalculation():
    bundle = generated_bundle()
    patch_assignment(
        bundle.assignments[0].id,
        PatchAssignmentRequest(plate="AA002AA", confirm=True),
    )
    recalculated = recalculate_planning(
        bundle.planning.id,
        RecalculatePlanningRequest(),
    )
    assert recalculated.assignments[0].plate == "AA002AA"
    assert recalculated.assignments[0].manual_override is True


def test_unconfirmed_assignment_is_recalculated():
    bundle = generated_bundle()
    patch_assignment(
        bundle.assignments[0].id,
        PatchAssignmentRequest(
            remove_vehicle=True,
            confirm=False,
            manual_override=False,
        ),
    )
    recalculated = recalculate_planning(
        bundle.planning.id,
        RecalculatePlanningRequest(),
    )
    assignment = recalculated.assignments[0]
    assert assignment.plate == "AA001AA"
    assert assignment.assignment_source == AssignmentSource.RECALCULATED


def test_simulate_driver_absent_proposes_unused_driver_without_persisting():
    bundle = generated_bundle()
    simulation = simulate_event(
        bundle.planning.id,
        event_request(
            OperationEventType.DRIVER_ABSENT,
            OperationEntityType.DRIVER,
            "driver01",
        ),
    )
    proposed = simulation.proposed_assignments[0]
    assert proposed.driver_id == "driver02"
    assert get_planning_bundle(bundle.planning.id).assignments[0].driver_id == "driver01"


def test_simulate_vehicle_ko_proposes_free_vehicle():
    bundle = generated_bundle()
    simulation = simulate_event(
        bundle.planning.id,
        event_request(
            OperationEventType.VEHICLE_UNAVAILABLE,
            OperationEntityType.VEHICLE,
            "AA001AA",
        ),
    )
    assert simulation.proposed_assignments[0].plate == "AA002AA"
    assert simulation.diff.assignment_changes


def test_simulate_route_abort_frees_driver_and_vehicle():
    bundle = generated_bundle()
    simulation = simulate_event(
        bundle.planning.id,
        event_request(
            OperationEventType.ROUTE_ABORTED,
            OperationEntityType.ROUTE,
            "R001",
        ),
    )
    proposed = simulation.proposed_assignments[0]
    assert proposed.driver_id is None
    assert proposed.plate is None
    assert proposed.assignment_status == AssignmentStatus.INVALIDATED


def test_apply_event_creates_new_version():
    bundle = generated_bundle()
    updated, event, _ = apply_event(
        bundle.planning.id,
        event_request(
            OperationEventType.ROUTE_ABORTED,
            OperationEntityType.ROUTE,
            "R001",
        ),
    )
    assert updated.planning.version == 2
    assert event.applied is True
    assert "ROUTE_ABORTED" in updated.assignments[0].warnings


def test_applied_route_abort_is_excluded_from_active_route_summary():
    bundle = generated_bundle(routes=2)
    updated, _, _ = apply_event(
        bundle.planning.id,
        event_request(
            OperationEventType.ROUTE_ABORTED,
            OperationEntityType.ROUTE,
            "R001",
        ),
    )
    assert updated.summary.routes_total == 1
    assert updated.summary.routes_assigned == 1
    assert updated.summary.routes_unassigned == 0
    assert "R001" not in updated.unassigned_routes


def test_history_contains_generation_manual_change_and_event():
    bundle = generated_bundle()
    patch_assignment(
        bundle.assignments[0].id,
        PatchAssignmentRequest(plate="AA002AA", confirm=True),
    )
    apply_event(
        bundle.planning.id,
        event_request(
            OperationEventType.ROUTE_ABORTED,
            OperationEntityType.ROUTE,
            "R001",
        ),
    )
    history = get_planning_bundle(bundle.planning.id).history
    assert len(history["versions"]) == 3
    assert len(history["events"]) == 2


def test_export_csv_contains_required_columns():
    bundle = generated_bundle()
    content = export_planning_csv(bundle.planning.id)
    rows = list(csv.DictReader(io.StringIO(content)))
    assert rows[0]["operation_date"] == "2026-07-20"
    assert rows[0]["route_id"] == "R001"
    assert "manual_override" in rows[0]


def test_manual_duplicate_vehicle_is_rejected():
    bundle = generated_bundle(routes=2, drivers=3, vehicles=3)
    with pytest.raises(AssignmentValidationError):
        patch_assignment(
            bundle.assignments[1].id,
            PatchAssignmentRequest(plate=bundle.assignments[0].plate),
        )


def test_manual_duplicate_driver_is_rejected():
    bundle = generated_bundle(routes=2, drivers=3, vehicles=3)
    with pytest.raises(AssignmentValidationError):
        patch_assignment(
            bundle.assignments[1].id,
            PatchAssignmentRequest(driver_id=bundle.assignments[0].driver_id),
        )
