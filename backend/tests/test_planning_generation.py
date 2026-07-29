import pytest

from app.domain.assignment_models import AssignmentSource, AssignmentStatus
from app.domain.normalized_models import NormalizedFleetRow
from app.domain.planning_models import PlanningConfiguration, StationRisk
from app.repositories.import_repository import save_import
from app.schemas.planning_schema import GeneratePlanningRequest
from app.services.planning_generation_service import generate_planning
from app.services.planning_validation_service import PlanningValidationError
from tests.planning_helpers import (
    realistic_normalized_rows,
    save_normalized_imports,
    save_realistic_imports,
    simple_rows,
)


def generate_simple(
    routes: int = 2,
    drivers: int = 3,
    vehicles: int = 3,
    configuration: PlanningConfiguration | None = None,
):
    planning, fleet = simple_rows(routes, drivers, vehicles)
    planning_id, fleet_id = save_normalized_imports(planning, fleet)
    return generate_planning(
        GeneratePlanningRequest(
            planning_import_id=planning_id,
            fleet_import_id=fleet_id,
            operation_date="2026-07-20",
            configuration=configuration,
        )
    )


def test_generate_planning_with_valid_imports():
    bundle = generate_simple()
    assert bundle.planning.id is not None
    assert bundle.summary.routes_total == 2
    assert len(bundle.assignments) == 2


def test_habitual_vehicle_available():
    bundle = generate_simple(routes=1, drivers=2, vehicles=2)
    assignment = bundle.assignments[0]
    assert assignment.plate == "AA001AA"
    assert assignment.assignment_source == AssignmentSource.HABITUAL_VEHICLE


def test_habitual_vehicle_unavailable():
    planning, fleet = simple_rows(routes=1, drivers=1, vehicles=2)
    fleet[0].status = "Officina"
    planning_id, fleet_id = save_normalized_imports(planning, fleet)
    bundle = generate_planning(
        GeneratePlanningRequest(
            planning_import_id=planning_id,
            fleet_import_id=fleet_id,
            operation_date="2026-07-20",
        )
    )
    assignment = bundle.assignments[0]
    assert assignment.plate == "AA002AA"
    assert "HABITUAL_VEHICLE_UNAVAILABLE" in assignment.warnings


def test_valid_imported_assignment_is_preserved():
    planning, fleet = simple_rows(routes=1, drivers=2, vehicles=2)
    planning[0].vehicle_plate = "AA002AA"
    planning_id, fleet_id = save_normalized_imports(planning, fleet)
    bundle = generate_planning(
        GeneratePlanningRequest(
            planning_import_id=planning_id,
            fleet_import_id=fleet_id,
            operation_date="2026-07-20",
        )
    )
    assert bundle.assignments[0].plate == "AA002AA"
    assert (
        bundle.assignments[0].assignment_source
        == AssignmentSource.IMPORTED_ASSIGNMENT
    )


def test_invalid_imported_assignment_is_blocked_with_alternatives():
    planning, fleet = simple_rows(routes=1, drivers=2, vehicles=2)
    planning[0].vehicle_plate = "ZZ999ZZ"
    planning_id, fleet_id = save_normalized_imports(planning, fleet)
    bundle = generate_planning(
        GeneratePlanningRequest(
            planning_import_id=planning_id,
            fleet_import_id=fleet_id,
            operation_date="2026-07-20",
        )
    )
    assignment = bundle.assignments[0]
    assert assignment.assignment_status == AssignmentStatus.BLOCKED
    assert assignment.alternatives


def test_duplicate_vehicle_is_reported():
    planning, fleet = simple_rows(routes=1, drivers=2, vehicles=2)
    fleet.append(fleet[0].model_copy(update={"row_number": 8}))
    planning_id, fleet_id = save_normalized_imports(planning, fleet)
    bundle = generate_planning(
        GeneratePlanningRequest(
            planning_import_id=planning_id,
            fleet_import_id=fleet_id,
            operation_date="2026-07-20",
        )
    )
    assert any(item.code == "DUPLICATE_VEHICLE" for item in bundle.conflicts)


def test_duplicate_driver_does_not_create_two_assignments():
    planning, fleet = simple_rows(routes=2, drivers=2, vehicles=2)
    planning[1].driver_name = planning[0].driver_name
    planning[1].driver_key = planning[0].driver_key
    planning_id, fleet_id = save_normalized_imports(planning, fleet)
    bundle = generate_planning(
        GeneratePlanningRequest(
            planning_import_id=planning_id,
            fleet_import_id=fleet_id,
            operation_date="2026-07-20",
        )
    )
    assert len([item for item in bundle.assignments if item.driver_id]) == 1
    assert any(item.code == "DUPLICATE_DRIVER" for item in bundle.conflicts)


def test_more_routes_than_vehicles_is_critical():
    bundle = generate_simple(routes=3, drivers=3, vehicles=2)
    capacity = bundle.station_capacity[0]
    assert capacity.readiness == StationRisk.CRITICAL
    assert capacity.operational_margin == -1


def test_more_routes_than_drivers_is_critical():
    bundle = generate_simple(routes=3, drivers=2, vehicles=3)
    capacity = bundle.station_capacity[0]
    assert capacity.readiness == StationRisk.CRITICAL
    assert capacity.drivers_available < capacity.routes_total


def test_reserve_below_threshold_is_medium_risk():
    bundle = generate_simple(
        routes=1,
        drivers=2,
        vehicles=2,
        configuration=PlanningConfiguration(
            reserve_vehicle_threshold_global=2
        ),
    )
    assert bundle.station_capacity[0].readiness == StationRisk.MEDIUM


def test_capacity_is_calculated_for_each_station():
    planning_id, fleet_id = save_realistic_imports()
    bundle = generate_planning(
        GeneratePlanningRequest(
            planning_import_id=planning_id,
            fleet_import_id=fleet_id,
            operation_date="2026-07-20",
        )
    )
    assert {item.station for item in bundle.station_capacity} == {"DLO1", "DLO2"}


def test_realistic_fixture_contains_station_deficit():
    planning_id, fleet_id = save_realistic_imports()
    bundle = generate_planning(
        GeneratePlanningRequest(
            planning_import_id=planning_id,
            fleet_import_id=fleet_id,
            operation_date="2026-07-20",
        )
    )
    dlo1 = next(item for item in bundle.station_capacity if item.station == "DLO1")
    assert dlo1.deficit_or_surplus == -1


def test_realistic_fixture_contains_station_surplus():
    planning_id, fleet_id = save_realistic_imports()
    bundle = generate_planning(
        GeneratePlanningRequest(
            planning_import_id=planning_id,
            fleet_import_id=fleet_id,
            operation_date="2026-07-20",
        )
    )
    dlo2 = next(item for item in bundle.station_capacity if item.station == "DLO2")
    assert dlo2.deficit_or_surplus == 2


def test_cross_station_is_suggested_but_not_applied():
    planning_id, fleet_id = save_realistic_imports()
    bundle = generate_planning(
        GeneratePlanningRequest(
            planning_import_id=planning_id,
            fleet_import_id=fleet_id,
            operation_date="2026-07-20",
            configuration=PlanningConfiguration(
                reserve_vehicle_threshold_by_station={"DLO1": 1, "DLO2": 1}
            ),
        )
    )
    dlo1 = next(item for item in bundle.station_capacity if item.station == "DLO1")
    assert dlo1.cross_station_suggestions
    assert dlo1.cross_station_suggestions[0].applied is False


def test_incompatible_station_imports_are_rejected():
    planning, fleet = simple_rows(routes=1, drivers=1, vehicles=1)
    fleet[0].station = "DLO2"
    planning_id, fleet_id = save_normalized_imports(planning, fleet)
    with pytest.raises(PlanningValidationError) as exc:
        generate_planning(
            GeneratePlanningRequest(
                planning_import_id=planning_id,
                fleet_import_id=fleet_id,
                operation_date="2026-07-20",
            )
        )
    assert exc.value.code == "INCOMPATIBLE_STATIONS"


def test_missing_planning_import_is_rejected():
    with pytest.raises(PlanningValidationError) as exc:
        generate_planning(
            GeneratePlanningRequest(operation_date="2026-07-20")
        )
    assert exc.value.code == "MISSING_PLANNING_IMPORT"


def test_missing_fleet_import_is_rejected():
    planning, _ = simple_rows(routes=1, drivers=1, vehicles=1)
    save_import(
        "planning",
        "planning-only.csv",
        None,
        [],
        [item.model_dump(mode="json") for item in planning],
    )
    with pytest.raises(PlanningValidationError) as exc:
        generate_planning(
            GeneratePlanningRequest(operation_date="2026-07-20")
        )
    assert exc.value.code == "MISSING_FLEET_IMPORT"


def test_realistic_fixture_shape():
    planning, fleet = realistic_normalized_rows()
    assert len(planning) == 20
    assert len({item.driver_key for item in fleet if item.driver_key}) == 22
    assert len(fleet) == 24
    assert sum(1 for item in fleet if item.status == "Officina") == 2
