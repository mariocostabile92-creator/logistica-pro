from app.domain.operation_events import OperationEventType
from app.domain.planning_models import DriverResource, VehicleResource
from app.utils.text_normalizer import normalize_plate


def apply_resource_event_constraints(
    drivers: list[DriverResource],
    vehicles: list[VehicleResource],
    events: list[dict[str, object]],
) -> tuple[list[DriverResource], list[VehicleResource]]:
    absent_drivers: set[str] = set()
    unavailable_vehicles: set[str] = set()
    for event in events:
        if not event.get("applied"):
            continue
        event_type = event["event_type"]
        entity_id = str(event["entity_id"])
        if event_type == OperationEventType.DRIVER_ABSENT.value:
            absent_drivers.add(entity_id)
        elif event_type == OperationEventType.DRIVER_RESTORED.value:
            absent_drivers.discard(entity_id)
        elif event_type == OperationEventType.VEHICLE_UNAVAILABLE.value:
            unavailable_vehicles.add(normalize_plate(entity_id))
        elif event_type == OperationEventType.VEHICLE_RESTORED.value:
            unavailable_vehicles.discard(normalize_plate(entity_id))

    effective_drivers = [
        item.model_copy(deep=True)
        for item in drivers
        if item.id not in absent_drivers
    ]
    effective_vehicles = [item.model_copy(deep=True) for item in vehicles]
    for vehicle in effective_vehicles:
        if vehicle.plate in unavailable_vehicles:
            vehicle.state = "blocked"
    return effective_drivers, effective_vehicles
