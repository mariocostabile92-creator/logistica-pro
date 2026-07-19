from app.domain.normalized_models import NormalizedFleetRow, NormalizedPlanningRow
from app.domain.operations_engine import OperationalCapacity
from app.services.conflict_service import is_operational_vehicle


def _route_key(row: NormalizedPlanningRow) -> str:
    return row.route or f"row-{row.row_number}"


def calculate_capacity(
    planning_rows: list[NormalizedPlanningRow],
    fleet_rows: list[NormalizedFleetRow],
) -> OperationalCapacity:
    routes = len({_route_key(row) for row in planning_rows})
    drivers = len({row.driver_key for row in planning_rows if row.driver_key})
    valid_plates = {row.vehicle_plate for row in fleet_rows if row.vehicle_plate}
    invalid_plate_records = sum(1 for row in fleet_rows if not row.vehicle_plate)
    operational_plates = {
        row.vehicle_plate
        for row in fleet_rows
        if row.vehicle_plate and is_operational_vehicle(row)
    }
    physical_vehicles = len(valid_plates) + invalid_plate_records
    operational_vehicles = len(operational_plates)
    operational_margin = operational_vehicles - routes

    return OperationalCapacity(
        routes=routes,
        drivers=drivers,
        physical_vehicles=physical_vehicles,
        operational_vehicles=operational_vehicles,
        reserve_vehicles=max(operational_margin, 0),
        blocked_vehicles=max(physical_vehicles - operational_vehicles, 0),
        operational_margin=operational_margin,
        driver_margin=drivers - routes,
    )
