from app.domain.normalized_models import NormalizedFleetRow, NormalizedPlanningRow
from app.services.capacity_service import calculate_capacity
from app.services.operations_engine import evaluate_operations


def planning_row(
    row_number: int,
    driver: str | None,
    plate: str,
    route: str,
) -> NormalizedPlanningRow:
    return NormalizedPlanningRow(
        row_number=row_number,
        driver_name=driver,
        driver_key=driver.lower() if driver else None,
        vehicle_plate=plate,
        route=route,
    )


def fleet_row(
    row_number: int,
    driver: str,
    plate: str,
    status: str = "Operativo",
) -> NormalizedFleetRow:
    return NormalizedFleetRow(
        row_number=row_number,
        driver_name=driver,
        driver_key=driver.lower(),
        vehicle_plate=plate,
        status=status,
    )


def test_operational_capacity():
    planning = [
        planning_row(2, "A", "AB123CD", "R1"),
        planning_row(3, "B", "EF456GH", "R2"),
    ]
    fleet = [
        fleet_row(2, "A", "AB123CD"),
        fleet_row(3, "B", "EF456GH"),
        fleet_row(4, "C", "IL789MN", "Officina"),
    ]

    capacity = calculate_capacity(planning, fleet)

    assert capacity.routes == 2
    assert capacity.physical_vehicles == 3
    assert capacity.operational_vehicles == 2
    assert capacity.blocked_vehicles == 1
    assert capacity.operational_margin == 0


def test_operational_summary():
    dashboard = evaluate_operations(
        [planning_row(2, "A", "AB123CD", "R1")],
        [
            fleet_row(2, "A", "AB123CD"),
            fleet_row(3, "B", "EF456GH"),
        ],
        reserve_threshold=1,
    )

    assert dashboard.summary.routes == 1
    assert dashboard.summary.drivers == 1
    assert dashboard.summary.physical_vehicles == 2
    assert dashboard.summary.reserve_vehicles == 1
    assert dashboard.summary.issues_count == 0


def test_operational_issues_have_reason_and_entity():
    dashboard = evaluate_operations(
        [planning_row(2, None, "AB123CD", "R1")],
        [fleet_row(2, "A", "AB123CD")],
    )

    issue = next(item for item in dashboard.issues if item.code == "ROUTE_WITHOUT_DRIVER")
    assert issue.severity.value == "critical"
    assert issue.reason
    assert issue.entity_ref == "R1"


def test_readiness_rules_green_yellow_red():
    green = evaluate_operations(
        [planning_row(2, "A", "AB123CD", "R1")],
        [
            fleet_row(2, "A", "AB123CD"),
            fleet_row(3, "B", "EF456GH"),
        ],
        reserve_threshold=1,
    )
    yellow = evaluate_operations(
        [
            planning_row(2, "A", "AB123CD", "R1"),
            planning_row(3, "B", "EF456GH", "R2"),
        ],
        [
            fleet_row(2, "A", "AB123CD"),
            fleet_row(3, "B", "EF456GH"),
        ],
        reserve_threshold=1,
    )
    red = evaluate_operations(
        [
            planning_row(2, "A", "AB123CD", "R1"),
            planning_row(3, "B", "EF456GH", "R2"),
        ],
        [
            fleet_row(2, "A", "AB123CD"),
            fleet_row(3, "B", "EF456GH", "Officina"),
        ],
        reserve_threshold=1,
    )

    assert green.readiness.status.value == "green"
    assert yellow.readiness.status.value == "yellow"
    assert "LOW_RESERVE_MARGIN" in yellow.readiness.triggered_rules
    assert red.readiness.status.value == "red"
    assert red.readiness.can_start_all_routes is False
