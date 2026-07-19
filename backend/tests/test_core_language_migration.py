import pytest

from app.domain.core_language import (
    AssetReference,
    CycleMapper,
    DriverMapper,
    HumanResource,
    OperationalUnit,
    ResourceAvailability,
    ResourceKind,
    RouteMapper,
    StationMapper,
    Task,
    TaskCancellationEvent,
    TimeWindow,
    VehicleMapper,
)


@pytest.mark.parametrize(
    ("mapper", "legacy_value", "core_type"),
    (
        (RouteMapper, "R001", Task),
        (StationMapper, "DLO1", OperationalUnit),
        (DriverMapper, "driver-001", HumanResource),
        (VehicleMapper, "AB123CD", AssetReference),
        (CycleMapper, "W1", TimeWindow),
    ),
)
def test_legacy_core_legacy_round_trip(
    mapper,
    legacy_value,
    core_type,
):
    core_value = mapper.to_core(legacy_value)

    assert isinstance(core_value, core_type)
    assert mapper.to_legacy(core_value) == legacy_value


def test_mappers_preserve_identifier_bytes_without_normalizing():
    legacy_route = " Route 01 "

    task = RouteMapper.to_core(legacy_route)

    assert task is not None
    assert task.external_identifier == legacy_route
    assert RouteMapper.to_legacy(task) == legacy_route


def test_mappers_preserve_missing_legacy_values():
    for mapper in (
        RouteMapper,
        StationMapper,
        DriverMapper,
        VehicleMapper,
        CycleMapper,
    ):
        assert mapper.to_core(None) is None
        assert mapper.to_legacy(None) is None
        assert mapper.to_core("") is None


def test_driver_mapper_can_carry_a_display_name_without_changing_identity():
    resource = DriverMapper.to_core(
        "driver-001",
        display_name="Driver Uno",
    )

    assert resource is not None
    assert resource.external_identifier == "driver-001"
    assert resource.display_name == "Driver Uno"
    assert DriverMapper.to_legacy(resource) == "driver-001"


def test_event_and_availability_models_use_neutral_references():
    task = Task(external_identifier="R001")
    cancellation = TaskCancellationEvent(
        task=task,
        reason="Operation cancelled",
        source_event_identifier="event-001",
    )
    availability = ResourceAvailability(
        resource_identifier="AB123CD",
        resource_kind=ResourceKind.ASSET,
        available=False,
        observed_state="unavailable",
    )

    assert cancellation.task == task
    assert availability.resource_kind is ResourceKind.ASSET
    assert availability.available is False


def test_core_models_do_not_expose_legacy_field_names():
    legacy_names = {
        "route",
        "station",
        "driver",
        "vehicle",
        "cycle",
    }
    core_models = (
        Task,
        OperationalUnit,
        HumanResource,
        AssetReference,
        TimeWindow,
        TaskCancellationEvent,
        ResourceAvailability,
    )

    for model in core_models:
        assert legacy_names.isdisjoint(model.model_fields)
