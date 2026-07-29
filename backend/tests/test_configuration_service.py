from app.adapters.amazon import AMAZON_ADAPTER
from app.core.configuration.models import (
    ConfigurationScope,
    ConfigurationValueSource,
)
from app.core.configuration.service import (
    create_configuration_version,
    get_current_configuration,
    get_generic_mapping_thresholds,
    list_configuration_versions,
    validate_configuration,
)
from app.services.normalization_service import suggest_mapping


def configuration_value(configuration, section_key, value_key):
    section = next(
        item
        for item in configuration.sections
        if item.key == section_key
    )
    return next(
        item
        for item in section.values
        if item.key == value_key
    )


def section(key, **values):
    return {
        "key": key,
        "values": [
            {"key": value_key, "value": value}
            for value_key, value in values.items()
        ],
    }


def test_safe_defaults_are_typed_valid_and_explainable():
    configuration = get_current_configuration()

    assert configuration.version.number == 0
    assert configuration.metadata.fallback_used is True
    assert len(configuration.sections) == 8
    assert configuration.metadata.validation_status == "valid"
    assert configuration.metadata.applied_versions == []
    assert configuration_value(
        configuration,
        "generic_mappings",
        "auto_mapping_min_confidence",
    ).source is ConfigurationValueSource.PLATFORM_DEFAULT
    assert get_generic_mapping_thresholds() == (0.78, 0.58)


def test_validation_rejects_incoherent_thresholds_and_secrets():
    invalid_thresholds = validate_configuration(
        [
            section(
                "generic_mappings",
                auto_mapping_min_confidence=0.5,
                review_mapping_min_confidence=0.8,
            )
        ]
    )
    secret_value = validate_configuration(
        [section("custom", api_key="not-allowed")]
    )

    assert invalid_thresholds.valid is False
    assert any(
        "soglia di revisione" in error
        for error in invalid_thresholds.errors
    )
    assert secret_value.valid is False
    assert any("segreti" in error for error in secret_value.errors)


def test_versions_are_immutable_and_latest_is_resolved():
    scope = ConfigurationScope(organization_id="org-one")
    first = create_configuration_version(
        scope,
        [section("nomenclature", asset_label="Equipment")],
        created_by="tester",
    )
    second = create_configuration_version(
        scope,
        [section("nomenclature", asset_label="Operational Asset")],
        created_by="tester",
    )
    versions = list_configuration_versions(scope)

    assert first.version.number == 1
    assert second.version.number == 2
    assert [item.number for item in versions] == [2, 1]
    assert configuration_value(
        second,
        "nomenclature",
        "asset_label",
    ).value == "Operational Asset"
    assert second.metadata.applied_versions[0].number == 2


def test_operational_unit_inherits_then_overrides_organization():
    organization_scope = ConfigurationScope(organization_id="org-two")
    unit_scope = ConfigurationScope(
        organization_id="org-two",
        operational_unit_id="unit-north",
    )
    create_configuration_version(
        organization_scope,
        [section("nomenclature", asset_label="Equipment")],
        created_by="tester",
    )
    create_configuration_version(
        unit_scope,
        [section("priorities", default="high")],
        created_by="tester",
    )

    configuration = get_current_configuration(unit_scope)
    asset_label = configuration_value(
        configuration,
        "nomenclature",
        "asset_label",
    )
    priority = configuration_value(
        configuration,
        "priorities",
        "default",
    )

    assert asset_label.value == "Equipment"
    assert asset_label.source is ConfigurationValueSource.ORGANIZATION
    assert priority.value == "high"
    assert priority.source is ConfigurationValueSource.OPERATIONAL_UNIT
    assert [item.number for item in configuration.metadata.applied_versions] == [
        1,
        1,
    ]


def test_future_adapter_scope_has_only_neutral_configuration():
    scope = ConfigurationScope(
        organization_id="org-three",
        adapter_id="future-source",
    )
    configuration = create_configuration_version(
        scope,
        [section("custom_mapping", external_status="internal_status")],
        created_by="tester",
    )

    value = configuration_value(
        configuration,
        "custom_mapping",
        "external_status",
    )
    assert value.source is ConfigurationValueSource.FUTURE_ADAPTER
    assert configuration.metadata.resolved_scope == scope


def test_normalization_reads_configured_generic_thresholds():
    create_configuration_version(
        ConfigurationScope(),
        [
            section(
                "generic_mappings",
                auto_mapping_min_confidence=0.95,
                review_mapping_min_confidence=0.9,
            )
        ],
        created_by="tester",
    )

    suggestion = suggest_mapping(
        ["Driver Extra"],
        AMAZON_ADAPTER.aliases_for("planning"),
    )[0]

    assert suggestion.target_field == "driver_name"
    assert suggestion.confidence == 0.92
    assert suggestion.requires_confirmation is True
