from app.adapters.amazon import AMAZON_ADAPTER
from app.adapters.amazon.event_types import AMAZON_EVENT_ALIASES
from app.adapters.amazon.field_aliases import (
    AMAZON_PLANNING_FIELD_ALIASES,
)
from app.adapters.registry import get_active_tabular_import_adapter
from app.core.configuration.models import ConfigurationScope
from app.core.configuration.service import create_configuration_version
from app.importers.adapter_contract import (
    AdapterMappingLifecycle,
    CoreConcept,
)
from app.services.normalization_service import suggest_mapping


def section(key, **values):
    return {
        "key": key,
        "values": [
            {"key": value_key, "value": value}
            for value_key, value in values.items()
        ],
    }


def test_amazon_adapter_is_the_active_versioned_contract():
    active = get_active_tabular_import_adapter()

    assert active is AMAZON_ADAPTER
    assert active.adapter_id == "amazon"
    assert active.contract_version == "1.0"
    assert active.recognized_operational_units() == {
        "dlo1",
        "dlo2",
        "mxp",
        "milano",
        "roma",
        "torino",
        "bologna",
        "deposito",
    }


def test_amazon_terms_map_to_stable_core_concepts():
    mappings = {
        item.external_term: (
            item.core_concept,
            item.compatibility_field,
            item.lifecycle,
        )
        for item in AMAZON_ADAPTER.concept_mappings()
    }

    assert mappings == {
        "route": (
            CoreConcept.TASK,
            "route",
            AdapterMappingLifecycle.ACTIVE,
        ),
        "station": (
            CoreConcept.OPERATIONAL_UNIT,
            "station",
            AdapterMappingLifecycle.ACTIVE,
        ),
        "wave": (
            CoreConcept.TIME_WINDOW,
            "cycle",
            AdapterMappingLifecycle.ACTIVE,
        ),
        "cycle": (
            CoreConcept.TIME_WINDOW,
            "cycle",
            AdapterMappingLifecycle.ACTIVE,
        ),
        "vehicle": (
            CoreConcept.ASSET,
            "vehicle_plate",
            AdapterMappingLifecycle.ACTIVE,
        ),
        "driver": (
            CoreConcept.HUMAN_RESOURCE,
            "driver_name",
            AdapterMappingLifecycle.ACTIVE,
        ),
        "yard": (
            CoreConcept.RESOURCE_POOL,
            None,
            AdapterMappingLifecycle.FUTURE,
        ),
        "dispatch": (
            CoreConcept.OPERATION_STATE_TRANSITION,
            None,
            AdapterMappingLifecycle.FUTURE,
        ),
        "scorecard": (
            CoreConcept.METRIC_OBSERVATION,
            None,
            AdapterMappingLifecycle.FUTURE,
        ),
    }


def test_amazon_events_map_to_stable_core_event_concepts():
    expected = {
        "abort": (
            CoreConcept.TASK_CANCELLATION_EVENT,
            "route_aborted",
        ),
        "route_abort": (
            CoreConcept.TASK_CANCELLATION_EVENT,
            "route_aborted",
        ),
        "van_down": (
            CoreConcept.ASSET_UNAVAILABLE_EVENT,
            "vehicle_unavailable",
        ),
        "driver_no_show": (
            CoreConcept.HUMAN_RESOURCE_UNAVAILABLE_EVENT,
            "driver_absent",
        ),
    }

    for external_event, contract in expected.items():
        mapping = AMAZON_ADAPTER.event_mapping_for(external_event)
        assert mapping is not None
        assert (
            mapping.core_concept,
            mapping.compatibility_event,
        ) == contract
        assert (
            AMAZON_ADAPTER.compatibility_event_for(external_event)
            == contract[1]
        )


def test_amazon_aliases_feed_the_generic_mapping_engine():
    mapping = suggest_mapping(
        [
            "Driver",
            "Vehicle",
            "Delivery Station",
            "Route ID",
            "Wave",
        ],
        AMAZON_ADAPTER.aliases_for("planning"),
    )

    assert {
        item.source_column: item.target_field
        for item in mapping
    } == {
        "Driver": "driver_name",
        "Vehicle": "vehicle_plate",
        "Delivery Station": "station",
        "Route ID": "route",
        "Wave": "cycle",
    }
    assert all(not item.requires_confirmation for item in mapping)


def test_configuration_engine_can_extend_amazon_aliases():
    create_configuration_version(
        ConfigurationScope(adapter_id="amazon"),
        [
            section(
                "generic_mappings",
                mappings={
                    "planning": {
                        "route": ["tour code"],
                    }
                },
            )
        ],
        created_by="contract-test",
    )

    aliases = AMAZON_ADAPTER.aliases_for("planning")
    suggestion = suggest_mapping(["Tour Code"], aliases)[0]

    assert "tour code" in aliases["route"]
    assert suggestion.target_field == "route"
    assert suggestion.requires_confirmation is False


def test_adapter_returns_defensive_contract_copies():
    aliases = AMAZON_ADAPTER.aliases_for("planning")
    mappings = AMAZON_ADAPTER.concept_mappings()
    aliases["route"].append("mutated")
    mappings.pop()

    assert "mutated" not in AMAZON_ADAPTER.aliases_for("planning")["route"]
    assert len(AMAZON_ADAPTER.concept_mappings()) == 9


def test_compatibility_exports_come_from_the_adapter_catalog():
    assert (
        AMAZON_PLANNING_FIELD_ALIASES
        == AMAZON_ADAPTER.base_aliases_for("planning")
    )
    assert AMAZON_EVENT_ALIASES == {
        "abort": "route_aborted",
        "route_abort": "route_aborted",
        "van_down": "vehicle_unavailable",
        "driver_no_show": "driver_absent",
    }
