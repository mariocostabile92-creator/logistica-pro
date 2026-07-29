from app.adapters.amazon import AMAZON_ADAPTER
from app.domain.normalized_models import NormalizedFleetRow, NormalizedPlanningRow
from app.services.conflict_service import analyze_operations


def codes(response):
    return {item.code for item in response.conflicts}


def test_driver_without_vehicle():
    response = analyze_operations(
        [NormalizedPlanningRow(row_number=2, driver_name="A", driver_key="a", route="R1")],
        [NormalizedFleetRow(row_number=2, vehicle_plate="AB123CD", driver_name="A", driver_key="a", status="Operativo")],
    )
    assert "DRIVER_WITHOUT_VEHICLE" in codes(response)


def test_duplicate_vehicle_multi_driver():
    response = analyze_operations(
        [
            NormalizedPlanningRow(row_number=2, driver_name="A", driver_key="a", vehicle_plate="AB123CD", route="R1"),
            NormalizedPlanningRow(row_number=3, driver_name="B", driver_key="b", vehicle_plate="AB123CD", route="R2"),
        ],
        [NormalizedFleetRow(row_number=2, vehicle_plate="AB123CD", driver_name="A", driver_key="a", status="Operativo")],
    )
    assert "VEHICLE_MULTI_DRIVER" in codes(response)


def test_unavailable_vehicle_assigned():
    response = analyze_operations(
        [NormalizedPlanningRow(row_number=2, driver_name="A", driver_key="a", vehicle_plate="AB123CD", route="R1")],
        [NormalizedFleetRow(row_number=2, vehicle_plate="AB123CD", driver_name="A", driver_key="a", status="Officina")],
    )
    assert "UNAVAILABLE_VEHICLE_ASSIGNED" in codes(response)


def test_insufficient_capacity():
    response = analyze_operations(
        [
            NormalizedPlanningRow(row_number=2, driver_name="A", driver_key="a", vehicle_plate="AB123CD", route="R1"),
            NormalizedPlanningRow(row_number=3, driver_name="B", driver_key="b", vehicle_plate="EF456GH", route="R2"),
        ],
        [NormalizedFleetRow(row_number=2, vehicle_plate="AB123CD", driver_name="A", driver_key="a", status="Operativo")],
    )
    assert "INSUFFICIENT_OPERATIONAL_VEHICLES" in codes(response)


def test_station_recognition_uses_the_adapter_contract():
    response = analyze_operations(
        [
            NormalizedPlanningRow(
                row_number=2,
                station="UNKNOWN",
                driver_name="A",
                driver_key="a",
                vehicle_plate="AB123CD",
                route="R1",
            )
        ],
        [
            NormalizedFleetRow(
                row_number=2,
                vehicle_plate="AB123CD",
                driver_name="A",
                driver_key="a",
                status="Operativo",
            )
        ],
        recognized_operational_units=(
            AMAZON_ADAPTER.recognized_operational_units()
        ),
    )

    assert "UNKNOWN_STATION" in codes(response)
