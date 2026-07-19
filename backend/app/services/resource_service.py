from app.domain.assignment_rules import vehicle_operational_state
from app.domain.normalized_models import NormalizedFleetRow, NormalizedPlanningRow
from app.domain.planning_models import (
    DriverResource,
    PlanningConfiguration,
    VehicleResource,
)


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
